from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import database  

# Inicialización de la API
app = FastAPI(
    title="GameDex Pro API",
    description="API para gestionar catálogos de videojuegos, usuarios y reseñas.",
    version="1.0.0"
)

# --- CONFIGURACIÓN DE CORS ---
# Crucial para que el frontend de tu amigo pueda conectarse desde cualquier lugar
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS DE DATOS (Pydantic) ---
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

class ResenaSchema(BaseModel):
    id_usuario: int
    puntuacion: int = Field(..., ge=1, le=5)
    comentario: str

# --- RUTAS DE CLIENTE ---

@app.get("/", tags=["General"])
def home():
    return {"mensaje": "¡GameDex Pro API está en línea!", "docs": "/docs"}

@app.get("/api/v1/juegos", tags=["Cliente"])
def listar_juegos():
    """Retorna todos los juegos disponibles en el catálogo."""
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM juegos")
        columnas = [column[0] for column in cursor.description]
        datos = [database.fila_a_dict(f) for f in cursor.fetchall()]
        conn.close()
        return {"total": len(datos), "datos": datos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al conectar con la base de datos: {e}")

@app.post("/api/v1/usuarios", tags=["Cliente"])
def crear_usuario(u: Usuario):
    """Registra un nuevo usuario en el sistema."""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (username, email) VALUES (%s, %s)", (u.username, u.email))
        conn.commit()
        return {"id": cursor.lastrowid, "mensaje": "Usuario creado con éxito"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"El usuario o email ya existe: {e}")
    finally:
        conn.close()

@app.post("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def agregar_coleccion(id_user: int, item: ColeccionItem):
    """Agrega un juego a la colección personal de un usuario."""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO colecciones (id_usuario, id_juego, estado, horas_jugadas) VALUES (%s, %s, %s, %s)",
            (id_user, item.id_juego, item.estado, item.horas_jugadas)
        )
        conn.commit()
        return {"mensaje": "Juego añadido a tu colección personal"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al añadir a colección: {e}")
    finally:
        conn.close()

@app.post("/api/v1/juegos/{id_juego}/resenas", tags=["Cliente"])
def dejar_resena(id_juego: int, r: ResenaSchema):
    """Permite a un usuario dejar una reseña en un juego."""
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO resenas (id_juego, id_usuario, puntuacion, comentario) VALUES (%s, %s, %s, %s)",
            (id_juego, r.id_usuario, r.puntuacion, r.comentario)
        )
        conn.commit()
        return {"mensaje": "Reseña publicada correctamente"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al guardar reseña: {e}")
    finally:
        conn.close()

# --- RUTAS DE ADMINISTRACIÓN ---

@app.post("/api/v1/admin/juegos", tags=["Admin"])
def registrar_juego(juego: Videojuego, x_token: str = Header(None)):
    """Añade un nuevo juego al catálogo (Requiere token de Admin)."""
    if x_token != "secret-admin-key":
        raise HTTPException(status_code=403, detail="No tienes permisos de administrador")
    
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        query = """INSERT INTO juegos (titulo, desarrollador, precio, clasificacion, imagen_url, generos, plataformas) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        valores = (
            juego.titulo, 
            juego.desarrollador, 
            juego.precio, 
            juego.clasificacion, 
            juego.imagen_url, 
            json.dumps(juego.generos), 
            json.dumps(juego.plataformas)
        )
        cursor.execute(query, valores)
        conn.commit()
        return {"id": cursor.lastrowid, "mensaje": "Juego registrado en el catálogo global"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en los datos del juego: {e}")
    finally:
        conn.close()

@app.delete("/api/v1/admin/juegos/{id_juego}", tags=["Admin"])
def borrar_juego(id_juego: int, x_token: str = Header(None)):
    """Elimina un juego del catálogo."""
    if x_token != "secret-admin-key":
        raise HTTPException(status_code=403, detail="Acceso denegado")
    
    conn = database.obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM juegos WHERE id = %s", (id_juego,))
        conn.commit()
        return {"mensaje": f"Juego con ID {id_juego} eliminado"}
    finally:
        conn.close()