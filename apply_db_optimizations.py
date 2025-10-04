#!/usr/bin/env python3
"""
Apply database optimizations from db_optimizations.sql
"""

from db import Database

def apply_optimizations():
    db = Database()

    # Read the SQL file
    with open('db_optimizations.sql', 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # Split by semicolon and execute each statement
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                if statement:
                    try:
                        print(f"Executing: {statement[:50]}...")
                        cur.execute(statement)
                        print("Success")
                    except Exception as e:
                        print(f"Error: {e}")
                        # Continue with other statements
            conn.commit()

    print("Database optimizations applied successfully!")

if __name__ == '__main__':
    apply_optimizations()