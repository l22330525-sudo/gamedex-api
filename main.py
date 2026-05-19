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
        
        # 1. Tabla de juegos
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
        
        # 2. Tabla de usuarios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE,
                email VARCHAR(100) UNIQUE
            )
        """)
        
        # 3. Tabla de colecciones (Historial del usuario)
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
        
        # MEJORA DE COLUMNA: Asegura que fecha_finalizado exista si la tabla es vieja
        try:
            cursor.execute("ALTER TABLE colecciones ADD COLUMN fecha_finalizado DATE NULL")
            conn.commit()
        except:
            pass

        # 4. Tabla de reseñas
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
        print("✅ Base de Datos estructurada con éxito.")
    except Exception as e:
        print(f"❌ Nota en DB: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

# Ejecutar creación de tablas al arrancar
crear_tablas_iniciales()

app = FastAPI(title="GameDex Pro API - Versión Blindada Final")

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

# --- RUTAS DE CLIENTE ---

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
        return {"total": len(datos), "datos": datos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al conectar con DB: {str(e)}")
    finally:
        if 'conn' in locals(): conn.close()

@app.get("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def ver_coleccion(id_user: int):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        query = """
            SELECT j.id as id_juego, j.titulo, c.estado, c.horas_jugadas, c.fecha_finalizado
            FROM colecciones c
            JOIN juegos j ON c.id_juego = j.id
            WHERE c.id_usuario = %s
        """
        cursor.execute(query, (id_user,))
        columnas = [column[0] for column in cursor.description]
        datos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
        return {"usuario_id": id_user, "total_en_coleccion": len(datos), "datos": datos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar colección: {str(e)}")
    finally:
        if 'conn' in locals(): conn.close()

@app.post("/api/v1/usuarios", tags=["Cliente"])
def crear_usuario(u: Usuario):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO usuarios (username, email) VALUES (%s, %s)", (u.username, u.email))
        conn.commit()
        return {"id_usuario": cursor.lastrowid, "mensaje": "Perfil creado"}
    except Exception:
        raise HTTPException(status_code=400, detail="El usuario o email ya existe")
    finally:
        if 'conn' in locals(): conn.close()

@app.post("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def agregar_coleccion(id_user: int, item: ColeccionItem):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        # VALIDACIÓN: ¿Existe el juego?
        cursor.execute("SELECT id FROM juegos WHERE id = %s", (item.id_juego,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"El juego con ID {item.id_juego} no existe.")

        cursor.execute(
            "INSERT INTO colecciones (id_usuario, id_juego, estado, horas_jugadas, fecha_finalizado) VALUES (%s, %s, %s, %s, %s)",
            (id_user, item.id_juego, item.estado, item.horas_jugadas, item.fecha_finalizado)
        )
        conn.commit()
        return {"mensaje": f"Juego añadido a la colección del usuario {id_user}"}
    except HTTPException as he: raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar en colección: {str(e)}")
    finally:
        if 'conn' in locals(): conn.close()

# --- RUTAS DE RESEÑAS ---

@app.post("/api/v1/juegos/{id_juego}/resenas", tags=["Reseñas"])
def dejar_resena(id_juego: int, r: ResenaSchema):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        
        # Verificar si el juego existe
        cursor.execute("SELECT id FROM juegos WHERE id = %s", (id_juego,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Juego no encontrado para reseñar")

        query = "INSERT INTO resenas (id_juego, id_usuario, puntuacion, comentario) VALUES (%s, %s, %s, %s)"
        cursor.execute(query, (id_juego, r.id_usuario, r.puntuacion, r.comentario))
        conn.commit()
        return {"mensaje": "Reseña publicada con éxito"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals(): conn.close()

# --- ESTADÍSTICAS ---

@app.get("/api/v1/usuarios/{id_user}/stats", tags=["Estadísticas"])
def obtener_estadisticas_usuario(id_user: int):
    try:
        conn = database.obtener_conexion()
        cursor = conn.cursor()
        query = """
            SELECT 
                COALESCE(SUM(horas_jugadas), 0) as total_horas, 
                COUNT(CASE WHEN estado = 'completado' THEN 1 END) as juegos_terminados
            FROM colecciones WHERE id_usuario = %s
        """
        cursor.execute(query, (id_user,))
        res = cursor.fetchone()
        return {
            "id_usuario": id_user,
            "horas_totales": res[0],
            "juegos_completados": res[1]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """
        cursor.execute(query, (
            juego.titulo, juego.desarrollador, juego.precio, 
            juego.clasificacion, juego.imagen_url, 
            json.dumps(juego.generos), json.dumps(juego.plataformas)
        ))
        conn.commit()
        return {"id": cursor.lastrowid, "mensaje": "Juego registrado exitosamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar: {str(e)}")
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
        return {"mensaje": f"Juego {id_juego} eliminado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals(): conn.close()