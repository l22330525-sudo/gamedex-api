import mysql.connector
import json
import os # <-- Importante para leer variables de Render

def obtener_conexion():
    # Intenta leer la configuración de la nube, si no existe, usa la de tu XAMPP
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "host.docker.internal"), 
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""), 
        database=os.getenv("DB_NAME", "gamedex_db"),
        port=int(os.getenv("DB_PORT", 3306))
    )

def fila_a_dict(fila):
    """
    Transforma una fila de MySQL en un diccionario de Python.
    Índices basados en tu captura de XAMPP:
    0:id, 1:titulo, 2:desarrollador, 4:precio, 5:clasificacion, 7:generos, 8:plataformas
    """
    return {
        "id": fila[0],
        "titulo": fila[1],
        "desarrollador": fila[2],
        "precio": float(fila[4]) if fila[4] else 0.0,
        "clasificacion": fila[5],
        "generos": json.loads(fila[7]) if fila[7] else [],
        "plataformas": json.loads(fila[8]) if fila[8] else []
    }