import logging
import mysql.connector
from mysql.connector import errorcode
import pandas as pd

logger = logging.getLogger(__name__)

def get_connection(db_config):
    """Establish and return a MySQL database connection."""
    try:
        connection = mysql.connector.connect(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database']
        )
        return connection
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            raise Exception("Invalid username or password")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            raise Exception(f"Database {db_config['database']} does not exist")
        else:
            raise Exception(f"MySQL Error: {err}")
    except Exception as e:
        raise Exception(f"Connection error: {str(e)}")

def test_connection(db_config):
    """Test the database connection."""
    conn = get_connection(db_config)
    conn.close()
    return True

def get_tables(db_config):
    """Get a list of tables in the database."""
    conn = get_connection(db_config)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SHOW TABLES")
        tables = [table[0] for table in cursor.fetchall()]
        return tables
    except mysql.connector.Error as err:
        logger.error(f"Error fetching tables: {err}")
        raise Exception(f"Error fetching tables: {err}")
    finally:
        cursor.close()
        conn.close()

def get_table_columns(db_config, table_name):
    """Get columns and their details for a specified table."""
    conn = get_connection(db_config)
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get column information
        cursor.execute(f"DESCRIBE `{table_name}`")
        columns = cursor.fetchall()
        
        # Format the response
        result = []
        for col in columns:
            result.append({
                'name': col['Field'],
                'type': col['Type'],
                'primary_key': col['Key'] == 'PRI',
                'nullable': col['Null'] == 'YES'
            })
        
        return result
    except mysql.connector.Error as err:
        logger.error(f"Error fetching table columns: {err}")
        raise Exception(f"Error fetching table columns: {err}")
    finally:
        cursor.close()
        conn.close()

def get_primary_key(db_config, table_name):
    """Get the primary key column(s) for a table."""
    conn = get_connection(db_config)
    cursor = conn.cursor()
    
    try:
        cursor.execute(f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = %s
              AND CONSTRAINT_NAME = 'PRIMARY'
            ORDER BY ORDINAL_POSITION
        """, (db_config['database'], table_name))
        
        primary_keys = [row[0] for row in cursor.fetchall()]
        return primary_keys
    except mysql.connector.Error as err:
        logger.error(f"Error fetching primary keys: {err}")
        raise Exception(f"Error fetching primary keys: {err}")
    finally:
        cursor.close()
        conn.close()

def create_table(db_config, table_name, column_defs, primary_key=None):
    """Create a new table in the database based on provided column definitions."""
    conn = get_connection(db_config)
    cursor = conn.cursor()
    
    try:
        # Build CREATE TABLE SQL statement
        columns_sql = []
        for col_name, col_type in column_defs.items():
            columns_sql.append(f"`{col_name}` {col_type}")
            
        # Add primary key constraint if specified
        if primary_key:
            columns_sql.append(f"PRIMARY KEY (`{primary_key}`)")
            
        create_sql = f"CREATE TABLE `{table_name}` ({', '.join(columns_sql)})"
        
        logger.debug(f"Creating table with SQL: {create_sql}")
        cursor.execute(create_sql)
        conn.commit()
        
        return True
    except mysql.connector.Error as err:
        logger.error(f"Error creating table: {err}")
        raise Exception(f"Error creating table: {err}")
    finally:
        cursor.close()
        conn.close()

def perform_sync(db_config, excel_file, table_name, column_mapping, primary_key=None, row_limit=None):
    """
    Synchronize data from Excel file to MySQL table using UPSERT logic.
    Returns statistics about the operation.
    
    Parameters:
        db_config: Database connection parameters
        excel_file: Path to Excel file
        table_name: MySQL table name
        column_mapping: Dictionary mapping Excel columns to DB columns
        primary_key: Primary key column for UPSERT logic (optional)
        row_limit: Optional limit on number of rows to process
    """
    logger.info(f"perform_sync started for table: {table_name}, primary_key: {primary_key}, row_limit: {row_limit}")
    
    # Verify database connection before starting
    logger.info("Testing database connection before starting sync...")
    test_connection(db_config)
    logger.info("Database connection successful, proceeding with sync")
    
    conn = get_connection(db_config)
    cursor = conn.cursor(dictionary=True)
    
    result = {
        'total_rows': 0,
        'inserted': 0,
        'updated': 0,
        'errors': 0,
        'error_messages': []
    }
    
    try:
        # Read Excel data
        logger.info(f"Reading Excel file: {excel_file}")
        df = pd.read_excel(excel_file)
        orig_row_count = len(df)
        result['total_rows'] = orig_row_count
        logger.info(f"Excel file contains {orig_row_count} rows")
        
        # Apply row limit if specified
        if row_limit and row_limit > 0 and len(df) > row_limit:
            logger.info(f"Limiting process to first {row_limit} rows out of {len(df)} based on user settings")
            df = df.head(row_limit)
            result['total_rows'] = len(df)
        # If no explicit limit, but we're in Replit with a large file, apply a safe limit
        elif row_limit is None and len(df) > 20:
            logger.info(f"No row limit specified but file is large. Applying default limit of 20 rows for Replit environment")
            df = df.head(20)
            result['total_rows'] = len(df)
        
        # Map Excel columns to DB columns
        df_mapped = pd.DataFrame()
        for excel_col, db_col in column_mapping.items():
            if excel_col in df.columns:
                df_mapped[db_col] = df[excel_col]
        
        # Get primary key if not provided but exists in table
        if not primary_key:
            try:
                pk = get_primary_key(db_config, table_name)
                if pk:
                    primary_key = pk[0]
            except:
                pass
        
        # Process one row at a time - safer in Replit
        rows_processed = 0
        
        # Use a much smaller batch size for Replit
        batch_size = 1
        
        for batch_idx in range(0, len(df_mapped), batch_size):
            batch_df = df_mapped.iloc[batch_idx:batch_idx+batch_size]
            
            for _, row in batch_df.iterrows():
                try:
                    # Convert NaN values to None and convert data types safely
                    row_dict = {}
                    row_values_debug = []
                    for k, v in row.items():
                        if pd.isna(v):
                            row_dict[k] = None
                            row_values_debug.append(f"{k}=NULL")
                        elif isinstance(v, (int, float)):
                            row_dict[k] = v
                            row_values_debug.append(f"{k}={v}")
                        else:
                            # Convert to string and truncate if needed (prevent oversized data)
                            val_str = str(v)
                            if len(val_str) > 250:  # Keep under VARCHAR(255) limit
                                val_str = val_str[:250]
                            row_dict[k] = val_str
                            row_values_debug.append(f"{k}={val_str[:20]}...")
                    
                    logger.info(f"Processing row {rows_processed + 1}: {', '.join(row_values_debug[:3])}...")
                    
                    # If we have a primary key, check if record exists
                    if primary_key and primary_key in row_dict and row_dict[primary_key] is not None:
                        # Check if record exists (safe query)
                        check_sql = f"SELECT 1 FROM `{table_name}` WHERE `{primary_key}` = %s LIMIT 1"
                        cursor.execute(check_sql, (row_dict[primary_key],))
                        record_exists = cursor.fetchone() is not None
                        
                        if record_exists:
                            # Perform UPDATE with timeout prevention
                            set_parts = []
                            values = []
                            
                            for col, val in row_dict.items():
                                if col != primary_key:
                                    set_parts.append(f"`{col}` = %s")
                                    values.append(val)
                            
                            values.append(row_dict[primary_key])  # For WHERE clause
                            
                            # Simplified UPDATE
                            update_sql = f"UPDATE `{table_name}` SET {', '.join(set_parts)} WHERE `{primary_key}` = %s"
                            
                            logger.info(f"Executing UPDATE query: {update_sql} with primary key: {row_dict[primary_key]}")
                            cursor.execute(update_sql, values)
                            result['updated'] += 1
                            logger.info(f"UPDATE successful for record with primary key: {row_dict[primary_key]}")
                        else:
                            # Perform INSERT
                            columns = list(row_dict.keys())
                            placeholders = ["%s"] * len(columns)
                            
                            # Simplified INSERT
                            insert_sql = f"INSERT INTO `{table_name}` (`{'`, `'.join(columns)}`) VALUES ({', '.join(placeholders)})"
                            
                            logger.info(f"Executing INSERT query: {insert_sql} with {len(columns)} columns")
                            values_list = list(row_dict.values())
                            cursor.execute(insert_sql, values_list)
                            result['inserted'] += 1
                            logger.info(f"INSERT successful, new record added")
                    else:
                        # No primary key, just INSERT
                        columns = list(row_dict.keys())
                        placeholders = ["%s"] * len(columns)
                        
                        # Simplified INSERT
                        insert_sql = f"INSERT INTO `{table_name}` (`{'`, `'.join(columns)}`) VALUES ({', '.join(placeholders)})"
                        
                        logger.info(f"Executing INSERT query (no PK): {insert_sql} with {len(columns)} columns")
                        values_list = list(row_dict.values())
                        cursor.execute(insert_sql, values_list)
                        result['inserted'] += 1
                        logger.info(f"INSERT successful, new record added (no PK match)")
                        
                    rows_processed += 1
                    
                    # Commit after EVERY row in Replit environment
                    conn.commit()
                    
                    # Более безопасный вывод сообщения о результате
                    operation_type = "Inserted"
                    if 'record_exists' in locals() and record_exists:
                        operation_type = "Updated"
                    logger.info(f"Row {rows_processed} processed successfully: {operation_type}")
                    
                except Exception as e:
                    conn.rollback()  # Rollback on error
                    logger.error(f"Error processing row {rows_processed}: {str(e)}")
                    result['errors'] += 1
                    result['error_messages'].append(str(e))
        
        # Log completion statistics
        logger.info(f"Sync completed. Processed {rows_processed} rows out of {orig_row_count}. Inserted: {result['inserted']}, Updated: {result['updated']}, Errors: {result['errors']}")
        
        # Add note about partial processing
        if orig_row_count > result['total_rows']:
            if row_limit:
                result['note'] = f"Ограничение: Обработано {result['total_rows']} строк из {orig_row_count} согласно заданному лимиту ({row_limit})"
            else:
                result['note'] = f"Внимание: Обработано только {result['total_rows']} строк из {orig_row_count} для предотвращения тайм-аутов в Replit"
        
        return result
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Sync error: {str(e)}")
        raise Exception(f"Error during synchronization: {str(e)}")
    finally:
        cursor.close()
        conn.close()
