from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date
import json
import database  

# --- BLOQUE DE CREACIÓN AUTOMÁTICA DE TABLAS ---
def crear_tablas_iniciales():
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS juegos (
                id INT AUTO_INCREMENT PRIMARY KEY,
                titulo VARCHAR(100) NOT NULL,
                desarrollador VARCHAR(100),
                precio DECIMAL(10, 2),
                clasificacion VARCHAR(10),
                imagen_url TEXT,
                generos JSON,
                plataformas JSON
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE,
                email VARCHAR(100) UNIQUE
            )
        """)
        
        # Agregamos 'fecha_finalizado' para el historial del cliente
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS colecciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_usuario INT,
                id_juego INT,
                estado VARCHAR(50),
                horas_jugadas INT DEFAULT 0,
                fecha_finalizado DATE NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resenas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_juego INT,
                id_usuario INT,
                puntuacion INT,
                comentario TEXT
            )
        """)
        
        conn.commit()
        print(" Base de Datos estructurada con éxito.")
    except Exception as e:
        print(f" Nota en DB: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

crear_tablas_iniciales()

app = FastAPI(title="GameDex Pro API - Full Version")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS DE DATOS ---
class Videojuego(BaseModel):
    titulo: str
    desarrollador: str
    precio: float = Field(..., ge=0)
    clasificacion: str
    generos: List[str]
    plataformas: List[str]
    imagen_url: Optional[str] = None

class Usuario(BaseModel):
    username: str
    email: str

class ColeccionItem(BaseModel):
    id_juego: int
    estado: str 
    horas_jugadas: int = 0
    fecha_finalizado: Optional[date] = None

class ResenaSchema(BaseModel):
    id_usuario: int
    puntuacion: int = Field(..., ge=1, le=5)
    comentario: str

# --- RUTAS DE CLIENTE (MEJORADAS) ---

@app.get("/api/v1/juegos", tags=["Cliente"])
def listar_juegos(genero: Optional[str] = Query(None, description="Filtrar por género")):
    """Retorna juegos. Opcionalmente filtra por género (ej. /juegos?genero=Accion)"""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        if genero:
            # Buscamos dentro del campo JSON de géneros
            cursor.execute("SELECT * FROM juegos WHERE JSON_CONTAINS(generos, %s)", (json.dumps(genero),))
        else:
            cursor.execute("SELECT * FROM juegos")
        
        columnas = [column[0] for column in cursor.description]
        datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        return {"total": len(datos), "datos": datos}
    finally:
        conn.close()

@app.get("/api/v1/juegos/top", tags=["Estadísticas"])
def obtener_top_juegos():
    """Devuelve los 5 juegos con mejor puntuación promedio"""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    query = """
        SELECT j.id, j.titulo, AVG(r.puntuacion) as promedio, COUNT(r.id) as total_resenas
        FROM juegos j
        JOIN resenas r ON j.id = r.id_juego
        GROUP BY j.id
        ORDER BY promedio DESC
        LIMIT 5
    """
    cursor.execute(query)
    columnas = [column[0] for column in cursor.description]
    datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    conn.close()
    return {"top_mejor_valorados": datos}

@app.get("/api/v1/usuarios/{id_user}/stats", tags=["Estadísticas"])
def obtener_estadisticas_usuario(id_user: int):
    """Calcula total de horas y juegos terminados de un usuario"""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    query = """
        SELECT 
            SUM(horas_jugadas) as total_horas, 
            COUNT(CASE WHEN estado = 'completado' THEN 1 END) as juegos_terminados
        FROM colecciones WHERE id_usuario = %s
    """
    cursor.execute(query, (id_user,))
    res = cursor.fetchone()
    conn.close()
    return {
        "id_usuario": id_user,
        "horas_totales_vida": res[0] if res[0] else 0,
        "medallas_completado": res[1]
    }

@app.get("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def ver_coleccion(id_user: int):
    """Muestra la lista personal del usuario con detalles del juego"""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    query = """
        SELECT j.titulo, c.estado, c.horas_jugadas, c.fecha_finalizado
        FROM colecciones c
        JOIN juegos j ON c.id_juego = j.id
        WHERE c.id_usuario = %s
    """
    cursor.execute(query, (id_user,))
    columnas = [column[0] for column in cursor.description]
    datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    conn.close()
    return {"usuario_id": id_user, "coleccion": datos}

# --- RUTAS DE REGISTRO BÁSICAS ---

@app.post("/api/v1/usuarios", tags=["Cliente"])
def crear_usuario(u: Usuario):
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (username, email) VALUES (%s, %s)", (u.username, u.email))
        conn.commit()
        return {"id_usuario": cursor.lastrowid, "mensaje": "Perfil creado"}
    except: raise HTTPException(status_code=400, detail="El usuario ya existe")
    finally: conn.close()

@app.post("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def agregar_coleccion(id_user: int, item: ColeccionItem):
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO colecciones (id_usuario, id_juego, estado, horas_jugadas, fecha_finalizado) VALUES (%s, %s, %s, %s, %s)",
            (id_user, item.id_juego, item.estado, item.horas_jugadas, item.fecha_finalizado)
        )
        conn.commit()
        return {"mensaje": f"Juego actualizado a {item.estado}"}
    finally: conn.close()

@app.post("/api/v1/juegos/{id_juego}/resenas", tags=["Cliente"])
def dejar_resena(id_juego: int, r: ResenaSchema):
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO resenas (id_juego, id_usuario, puntuacion, comentario) VALUES (%s, %s, %s, %s)",
                       (id_juego, r.id_usuario, r.puntuacion, r.comentario))
        conn.commit()
        return {"mensaje": "Reseña guardada"}
    finally: conn.close()

# --- RUTAS DE ADMINISTRACIÓN ---

@app.post("/api/v1/admin/juegos", tags=["Admin"])
def registrar_juego(juego: Videojuego, x_token: str = Header(None)):
    if x_token != "secret-admin-key":
        raise HTTPException(status_code=403, detail="Sin permiso")
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        query = "INSERT INTO juegos (titulo, desarrollador, precio, clasificacion, imagen_url, generos, plataformas) VALUES (%s,%s,%s,%s,%s,%s,%s)"
        cursor.execute(query, (juego.titulo, juego.desarrollador, juego.precio, juego.clasificacion, juego.imagen_url, json.dumps(juego.generos), json.dumps(juego.plataformas)))
        conn.commit()
        return {"id": cursor.lastrowid, "mensaje": "Catálogo actualizado"}
    finally: conn.close()

@app.delete("/api/v1/admin/juegos/{id_juego}", tags=["Admin"])
def borrar_juego(id_juego: int, x_token: str = Header(None)):
    if x_token != "secret-admin-key": raise HTTPException(status_code=403, detail="Denegado")
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM juegos WHERE id = %s", (id_juego,))
    conn.commit()
    conn.close()
    return {"mensaje": "Juego eliminado"}