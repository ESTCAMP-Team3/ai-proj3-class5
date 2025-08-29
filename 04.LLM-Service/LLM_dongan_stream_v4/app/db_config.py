import mysql.connector
import os

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "mysql.dongango.com"),
            user=os.getenv("DB_USER", "class5"),
            password=os.getenv("DB_PASS", "zmffotm5"),
            database=os.getenv("DB_NAME", "ai3class5"),
            auth_plugin="mysql_native_password"
        )
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        raise


