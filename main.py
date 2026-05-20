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
        
        # 1. Tabla de juegos (Catálogo principal)
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
        
        # 2. Tabla de usuarios (Mejorada con Password para el Login)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE,
                email VARCHAR(100) UNIQUE,
                password VARCHAR(100) NOT NULL
            )
        """)
        
        # Parche de seguridad: Asegurar que password exista si la tabla ya era vieja
        try:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN password VARCHAR(100) NOT NULL DEFAULT '12345'")
            conn.commit()
        except:
            pass

        # 3. Tabla de colecciones (Sin el campo de fecha de finalización)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS colecciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_usuario INT,
                id_juego INT,
                estado VARCHAR(50),
                horas_jugadas INT DEFAULT 0
            )
        """)
        
        # 4. Tabla de reseñas (Comentarios de los jugadores)
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
        print("✅ Base de Datos estructurada y actualizada con éxito (Sin Fechas).")

    except Exception as e:
        print(f"❌ Nota en la Base de Datos: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

# Ejecutar la creación de tablas al arrancar el servidor
crear_tablas_iniciales()

app = FastAPI(title="GameDex Pro API - Sistema de Autenticación Completo")

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS DE DATOS (SCHEMAS) ---

class Videojuego(BaseModel):
    titulo: str
    desarrollador: str
    precio: float = Field(..., ge=0)
    clasificacion: str
    generos: List[str]
    plataformas: List[str]
    imagen_url: Optional[str] = None

class UsuarioRegistro(BaseModel):
    username: str
    email: str
    password: str

class UsuarioLogin(BaseModel):
    email: str
    password: str

class ColeccionItem(BaseModel):
    id_juego: int
    estado: str 
    horas_jugadas: int = 0
    # Se eliminó fecha_finalizado de aquí

class ResenaSchema(BaseModel):
    id_usuario: int
    puntuacion: int = Field(..., ge=1, le=5)
    comentario: str

# --- RUTAS DE AUTENTICACIÓN (LOGIN Y REGISTRO) ---

@app.post("/api/v1/auth/registrar", tags=["Autenticación"])
def registrar_usuario(u: UsuarioRegistro):
    """Permite a un nuevo usuario crear una cuenta con contraseña."""
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = "INSERT INTO usuarios (username, email, password) VALUES (%s, %s, %s)"
        valores = (u.username, u.email, u.password)
        
        cursor.execute(query, valores)
        conn.commit()
        
        return {"id_usuario": cursor.lastrowid, "mensaje": "Usuario registrado exitosamente"}
    except Exception:
        raise HTTPException(status_code=400, detail="El nombre de usuario o email ya están registrados")
    finally:
        if 'conn' in locals(): conn.close()

@app.post("/api/v1/auth/login", tags=["Autenticación"])
def login(credenciales: UsuarioLogin):
    """Verifica el correo y contraseña para permitir el ingreso."""
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = "SELECT id, username, email FROM usuarios WHERE email = %s AND password = %s"
        cursor.execute(query, (credenciales.email, credenciales.password))
        resultado = cursor.fetchone()
        
        if resultado:
            return {
                "mensaje": "Inicio de sesión exitoso",
                "usuario": {
                    "id": resultado[0], 
                    "username": resultado[1], 
                    "email": resultado[2]
                }
            }
        else:
            raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    finally:
        if 'conn' in locals(): conn.close()

# --- RUTAS DE CLIENTE (CATÁLOGO Y COLECCIÓN) ---

@app.get("/api/v1/juegos", tags=["Cliente"])
def listar_juegos(genero: Optional[str] = Query(None, description="Filtrar por género")):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        if genero:
            cursor.execute("SELECT * FROM juegos WHERE JSON_CONTAINS(generos, %s)", (json.dumps(genero),))
        else:
            cursor.execute("SELECT * FROM juegos")
        
        columnas = [column[0] for column in cursor.description]
        datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        
        return {"total_juegos": len(datos), "datos": datos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en DB: {str(e)}")
    finally:
        if 'conn' in locals(): conn.close()

@app.get("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def ver_coleccion(id_user: int):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        # Query actualizado: ya no selecciona fecha_finalizado
        query = """
            SELECT j.id as id_juego, j.titulo, c.estado, c.horas_jugadas
            FROM colecciones c
            JOIN juegos j ON c.id_juego = j.id
            WHERE c.id_usuario = %s
        """
        cursor.execute(query, (id_user,))
        
        columnas = [column[0] for column in cursor.description]
        datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        
        return {"usuario_id": id_user, "total_items": len(datos), "datos": datos}
    finally:
        if 'conn' in locals(): conn.close()

@app.post("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def agregar_coleccion(id_user: int, item: ColeccionItem):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM juegos WHERE id = %s", (item.id_juego,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"El juego {item.id_juego} no existe.")

        # Query actualizado: ya no inserta fecha_finalizado
        query = """
            INSERT INTO colecciones (id_usuario, id_juego, estado, horas_jugadas) 
            VALUES (%s, %s, %s, %s)
        """
        valores = (id_user, item.id_juego, item.estado, item.horas_jugadas)
        
        cursor.execute(query, valores)
        conn.commit()
        
        return {"mensaje": "Juego añadido correctamente a tu colección"}
    finally:
        if 'conn' in locals(): conn.close()

# --- RUTAS DE RESEÑAS ---

@app.post("/api/v1/juegos/{id_juego}/resenas", tags=["Reseñas"])
def dejar_resena(id_juego: int, r: ResenaSchema):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM juegos WHERE id = %s", (id_juego,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="No se puede reseñar un juego que no existe")

        query = "INSERT INTO resenas (id_juego, id_usuario, puntuacion, comentario) VALUES (%s, %s, %s, %s)"
        valores = (id_juego, r.id_usuario, r.puntuacion, r.comentario)
        
        cursor.execute(query, valores)
        conn.commit()
        
        return {"mensaje": "¡Reseña publicada con éxito!"}
    finally:
        if 'conn' in locals(): conn.close()

@app.get("/api/v1/juegos/{id_juego}/resenas", tags=["Reseñas"])
def ver_resenas(id_juego: int):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM resenas WHERE id_juego = %s", (id_juego,))
        
        columnas = [column[0] for column in cursor.description]
        datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        
        return datos
    finally:
        if 'conn' in locals(): conn.close()

# --- ESTADÍSTICAS ---

@app.get("/api/v1/usuarios/{id_user}/stats", tags=["Estadísticas"])
def obtener_estadisticas_usuario(id_user: int):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = """
            SELECT COALESCE(SUM(horas_jugadas), 0), COUNT(*) 
            FROM colecciones WHERE id_usuario = %s
        """
        cursor.execute(query, (id_user,))
        res = cursor.fetchone()
        
        return {
            "id_usuario": id_user, 
            "horas_totales_jugadas": res[0], 
            "juegos_en_coleccion": res[1]
        }
    finally:
        if 'conn' in locals(): conn.close()

# --- ADMINISTRACIÓN ---

@app.post("/api/v1/admin/juegos", tags=["Admin"])
def registrar_juego(juego: Videojuego, x_token: str = Header(None)):
    if x_token != "secret-admin-key":
        raise HTTPException(status_code=403, detail="Token de administrador no válido")
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = """
            INSERT INTO juegos (titulo, desarrollador, precio, clasificacion, imagen_url, generos, plataformas) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        valores = (
            juego.titulo, juego.desarrollador, juego.precio, 
            juego.clasificacion, juego.imagen_url, 
            json.dumps(juego.generos), json.dumps(juego.plataformas)
        )
        
        cursor.execute(query, valores)
        conn.commit()
        
        return {"id_nuevo_juego": cursor.lastrowid, "mensaje": "Juego dado de alta exitosamente"}
    finally:
        if 'conn' in locals(): conn.close()

@app.delete("/api/v1/admin/juegos/{id_juego}", tags=["Admin"])
def borrar_juego(id_juego: int, x_token: str = Header(None)):
    if x_token != "secret-admin-key":
        raise HTTPException(status_code=403, detail="Acceso denegado")
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM juegos WHERE id = %s", (id_juego,))
        conn.commit()
        
        return {"mensaje": f"El juego con ID {id_juego} ha sido eliminado del catálogo"}
    finally:
        if 'conn' in locals(): conn.close()