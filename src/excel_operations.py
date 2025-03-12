import pandas as pd
import logging

logger = logging.getLogger(__name__)

def validate_excel_file(file_path):
    """
    Validate that the file is a valid Excel file that can be processed.
    Raises an exception if the file is invalid.
    """
    try:
        # Attempt to read the file
        df = pd.read_excel(file_path)
        
        # Check if there's data
        if len(df) == 0:
            raise Exception("Excel file contains no data")
        
        # Check if there are columns
        if len(df.columns) == 0:
            raise Exception("Excel file contains no columns")
            
        return True
    except pd.errors.EmptyDataError:
        raise Exception("Excel file is empty")
    except pd.errors.ParserError:
        raise Exception("File is not a valid Excel file")
    except Exception as e:
        logger.error(f"Excel validation error: {str(e)}")
        raise Exception(f"Error validating Excel file: {str(e)}")

def get_excel_columns(file_path):
    """
    Get a list of column names from the Excel file.
    """
    try:
        df = pd.read_excel(file_path)
        return list(df.columns)
    except Exception as e:
        logger.error(f"Error reading Excel columns: {str(e)}")
        raise Exception(f"Error reading Excel columns: {str(e)}")

def get_excel_preview(file_path, rows=5):
    """
    Get a preview of the Excel data (first few rows).
    """
    try:
        df = pd.read_excel(file_path)
        preview = df.head(rows)
        
        # Convert the preview to a list of dictionaries for easier template rendering
        preview_dict = preview.to_dict(orient="records")
        columns = list(df.columns)
        
        return {
            'columns': columns,
            'data': preview_dict
        }
    except Exception as e:
        logger.error(f"Error generating Excel preview: {str(e)}")
        raise Exception(f"Error generating Excel preview: {str(e)}")

def infer_column_types(file_path):
    """
    Infer MySQL column types from Excel data.
    """
    try:
        df = pd.read_excel(file_path)
        column_types = {}
        
        for col in df.columns:
            # Check for numeric columns
            if pd.api.types.is_numeric_dtype(df[col]):
                # Check if it's integer-like
                if df[col].dropna().apply(lambda x: x.is_integer() if hasattr(x, 'is_integer') else True).all():
                    # Check for size
                    max_val = df[col].max()
                    min_val = df[col].min()
                    
                    if pd.isna(max_val) or pd.isna(min_val):
                        column_types[col] = 'INT'
                    elif min_val >= 0:
                        if max_val <= 255:
                            column_types[col] = 'TINYINT UNSIGNED'
                        elif max_val <= 65535:
                            column_types[col] = 'SMALLINT UNSIGNED'
                        elif max_val <= 16777215:
                            column_types[col] = 'MEDIUMINT UNSIGNED'
                        elif max_val <= 4294967295:
                            column_types[col] = 'INT UNSIGNED'
                        else:
                            column_types[col] = 'BIGINT UNSIGNED'
                    else:
                        if min_val >= -128 and max_val <= 127:
                            column_types[col] = 'TINYINT'
                        elif min_val >= -32768 and max_val <= 32767:
                            column_types[col] = 'SMALLINT'
                        elif min_val >= -8388608 and max_val <= 8388607:
                            column_types[col] = 'MEDIUMINT'
                        elif min_val >= -2147483648 and max_val <= 2147483647:
                            column_types[col] = 'INT'
                        else:
                            column_types[col] = 'BIGINT'
                else:
                    # It's a float/double
                    column_types[col] = 'DOUBLE'
            
            # Check for datetime
            elif pd.api.types.is_datetime64_dtype(df[col]):
                column_types[col] = 'DATETIME'
            
            # Check for date
            elif pd.api.types.is_period_dtype(df[col]):
                column_types[col] = 'DATE'
            
            # Default to VARCHAR
            else:
                # Calculate max length
                max_length = df[col].astype(str).str.len().max()
                if pd.isna(max_length) or max_length <= 0:
                    max_length = 255
                
                if max_length <= 255:
                    column_types[col] = f'VARCHAR({max_length})'
                elif max_length <= 65535:
                    column_types[col] = 'TEXT'
                elif max_length <= 16777215:
                    column_types[col] = 'MEDIUMTEXT'
                else:
                    column_types[col] = 'LONGTEXT'
        
        return column_types
    except Exception as e:
        logger.error(f"Error inferring column types: {str(e)}")
        return {col: 'VARCHAR(255)' for col in get_excel_columns(file_path)}
