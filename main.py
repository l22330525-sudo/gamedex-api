from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Any
from datetime import date
import json
import database  

# =================================================================
# --- BLOQUE DE CREACIÓN AUTOMÁTICA DE TABLAS ---
# =================================================================

def crear_tablas_iniciales():
    """
    Se encarga de verificar que la base de datos tenga la estructura necesaria
    al momento de iniciar la aplicación.
    """
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        # 1. Tabla de juegos (Catálogo principal)
        # ---------------------------------------------------------
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
        
        # 2. Tabla de usuarios (Mejorada para soportar Login)
        # ---------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE,
                email VARCHAR(100) UNIQUE,
                password VARCHAR(100) NOT NULL
            )
        """)
        
        # Parche de seguridad para tablas antiguas
        try:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN password VARCHAR(100) NOT NULL DEFAULT '12345'")
            conn.commit()
        except:
            pass

        # 3. Tabla de colecciones (Vincula usuarios con sus juegos)
        # ---------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS colecciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_usuario INT,
                id_juego INT,
                estado VARCHAR(50),
                horas_jugadas INT DEFAULT 0
            )
        """)
        
        # 4. Tabla de reseñas (Comunidad y feedback)
        # ---------------------------------------------------------
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
        print("✅ Base de Datos estructurada y actualizada con éxito.")

    except Exception as e:
        print(f"❌ Error crítico en la Base de Datos: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

# Ejecución de la configuración inicial
crear_tablas_iniciales()

# Instancia de FastAPI con metadatos
app = FastAPI(
    title="GameDex Pro API",
    description="API para la gestión de catálogos de videojuegos, colecciones personales y reseñas.",
    version="2.0.0"
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =================================================================
# --- MODELOS DE DATOS (SCHEMAS) CON VALIDACIÓN BLINDADA ---
# =================================================================

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
    horas_jugadas: Any = 0

    @validator('horas_jugadas')
    def limpiar_horas(cls, v):
        """Mejora: Si el frontend manda un string o 'undefined', lo vuelve 0."""
        try:
            return int(v) if v else 0
        except (ValueError, TypeError):
            return 0

class ResenaSchema(BaseModel):
    id_usuario: Any 
    puntuacion: int = Field(..., ge=1, le=5)
    comentario: str

    @validator('id_usuario')
    def validar_id_usuario(cls, v):
        """Mejora: Si el ID viene como string o roto, lo intenta convertir o falla con aviso."""
        try:
            return int(v)
        except (ValueError, TypeError):
            raise ValueError("ID de usuario inválido (debe ser un número). Verifica el Login.")

# =================================================================
# --- RUTAS DE AUTENTICACIÓN ---
# =================================================================

@app.post("/api/v1/auth/registrar", tags=["Autenticación"])
def registrar_usuario(u: UsuarioRegistro):
    """Crea una nueva cuenta de usuario en el sistema."""
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = "INSERT INTO usuarios (username, email, password) VALUES (%s, %s, %s)"
        valores = (u.username, u.email, u.password)
        
        cursor.execute(query, valores)
        conn.commit()
        
        return {"id_usuario": cursor.lastrowid, "mensaje": "Usuario registrado exitosamente"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="El nombre de usuario o email ya existen.")
    finally:
        if 'conn' in locals(): conn.close()

@app.post("/api/v1/auth/login", tags=["Autenticación"])
def login(credenciales: UsuarioLogin):
    """Verifica credenciales y devuelve los datos del usuario logueado."""
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
            raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")
    finally:
        if 'conn' in locals(): conn.close()

# =================================================================
# --- RUTAS DE CLIENTE (CATÁLOGO Y COLECCIÓN) ---
# =================================================================

@app.get("/api/v1/juegos", tags=["Cliente"])
def listar_juegos(genero: Optional[str] = Query(None, description="Filtrar por género")):
    """Obtiene la lista de juegos disponibles en el catálogo."""
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        if genero:
            query = "SELECT * FROM juegos WHERE JSON_CONTAINS(generos, %s)"
            cursor.execute(query, (json.dumps(genero),))
        else:
            query = "SELECT * FROM juegos"
            cursor.execute(query)
        
        columnas = [column[0] for column in cursor.description]
        datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        
        return {"total": len(datos), "datos": datos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals(): conn.close()

@app.get("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def ver_coleccion(id_user: Any):
    """Devuelve la colección personal de un usuario específico."""
    try:
        user_id_clean = int(id_user)
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = """
            SELECT j.id as id_juego, j.titulo, c.estado, c.horas_jugadas
            FROM colecciones c
            JOIN juegos j ON c.id_juego = j.id
            WHERE c.id_usuario = %s
        """
        cursor.execute(query, (user_id_clean,))
        
        columnas = [column[0] for column in cursor.description]
        datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        
        return {"usuario_id": user_id_clean, "total_items": len(datos), "datos": datos}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="ID de usuario no válido en la URL.")
    finally:
        if 'conn' in locals(): conn.close()

@app.post("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def agregar_coleccion(id_user: Any, item: ColeccionItem):
    """Agrega un juego a la colección del usuario logueado."""
    try:
        user_id_clean = int(id_user)
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        # Validación de existencia del juego
        cursor.execute("SELECT titulo FROM juegos WHERE id = %s", (item.id_juego,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"El juego con ID {item.id_juego} no existe.")

        query = """
            INSERT INTO colecciones (id_usuario, id_juego, estado, horas_jugadas) 
            VALUES (%s, %s, %s, %s)
        """
        valores = (user_id_clean, item.id_juego, item.estado, item.horas_jugadas)
        
        cursor.execute(query, valores)
        conn.commit()
        
        return {"mensaje": "Juego añadido exitosamente a la colección."}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="ID de usuario inválido.")
    finally:
        if 'conn' in locals(): conn.close()

# =================================================================
# --- RUTAS DE RESEÑAS ---
# =================================================================

@app.post("/api/v1/juegos/{id_juego}/resenas", tags=["Reseñas"])
def dejar_resena(id_juego: int, r: ResenaSchema):
    """Permite publicar una opinión sobre un juego."""
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM juegos WHERE id = %s", (id_juego,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="El juego no existe.")

        query = """
            INSERT INTO resenas (id_juego, id_usuario, puntuacion, comentario) 
            VALUES (%s, %s, %s, %s)
        """
        valores = (id_juego, int(r.id_usuario), r.puntuacion, r.comentario)
        
        cursor.execute(query, valores)
        conn.commit()
        
        return {"mensaje": "¡Reseña publicada con éxito!"}
    finally:
        if 'conn' in locals(): conn.close()

@app.get("/api/v1/juegos/{id_juego}/resenas", tags=["Reseñas"])
def ver_resenas(id_juego: int):
    """Muestra todas las reseñas de un juego."""
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = "SELECT * FROM resenas WHERE id_juego = %s"
        cursor.execute(query, (id_juego,))
        
        columnas = [column[0] for column in cursor.description]
        datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        
        return datos
    finally:
        if 'conn' in locals(): conn.close()

# =================================================================
# --- ESTADÍSTICAS ---
# =================================================================

@app.get("/api/v1/usuarios/{id_user}/stats", tags=["Estadísticas"])
def obtener_estadisticas_usuario(id_user: Any):
    """Calcula las horas totales y cantidad de juegos de un usuario."""
    try:
        user_id_clean = int(id_user)
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = """
            SELECT COALESCE(SUM(horas_jugadas), 0), COUNT(*) 
            FROM colecciones WHERE id_usuario = %s
        """
        cursor.execute(query, (user_id_clean,))
        res = cursor.fetchone()
        
        return {
            "id_usuario": user_id_clean, 
            "horas_totales_jugadas": int(res[0]), 
            "juegos_en_coleccion": res[1]
        }
    except:
        return {"error": "No se pudieron obtener estadísticas para este ID."}
    finally:
        if 'conn' in locals(): conn.close()

# =================================================================
# --- ADMINISTRACIÓN ---
# =================================================================

@app.post("/api/v1/admin/juegos", tags=["Admin"])
def registrar_juego(juego: Videojuego, x_token: str = Header(None)):
    """Añade un nuevo juego al catálogo global (Solo Admin)."""
    if x_token != "secret-admin-key":
        raise HTTPException(status_code=403, detail="No tienes permisos de administrador.")
    
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
        
        return {"id_nuevo_juego": cursor.lastrowid, "mensaje": "Juego dado de alta."}
    finally:
        if 'conn' in locals(): conn.close()

@app.delete("/api/v1/admin/juegos/{id_juego}", tags=["Admin"])
def borrar_juego(id_juego: int, x_token: str = Header(None)):
    """Elimina un juego del catálogo global (Solo Admin)."""
    if x_token != "secret-admin-key":
        raise HTTPException(status_code=403, detail="Acceso denegado.")
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        query = "DELETE FROM juegos WHERE id = %s"
        cursor.execute(query, (id_juego,))
        conn.commit()
        
        return {"mensaje": f"Juego {id_juego} eliminado permanentemente."}
    finally:
        if 'conn' in locals(): conn.close()