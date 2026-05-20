from fastapi import FastAPI, HTTPException, Header, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Any
from datetime import date
import json
import database  

# =================================================================
# --- BLOQUE DE CONFIGURACIÓN Y BASE DE DATOS ---
# =================================================================

def crear_tablas_iniciales():
    """
    Función encargada de la persistencia de datos inicial.
    Verifica la existencia de tablas y aplica parches de seguridad.
    """
    try:
        print("--- Iniciando verificación de tablas ---")
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
        
        # 2. Tabla de usuarios (Gestión de perfiles)
        # ---------------------------------------------------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE,
                email VARCHAR(100) UNIQUE,
                password VARCHAR(100) NOT NULL
            )
        """)
        
        # Parche de seguridad para compatibilidad de versiones
        try:
            print("Verificando integridad de la tabla usuarios...")
            cursor.execute("ALTER TABLE usuarios ADD COLUMN password VARCHAR(100) NOT NULL DEFAULT '12345'")
            conn.commit()
        except:
            print("La columna password ya existe o no es necesaria actualizar.")

        # 3. Tabla de colecciones (Estadísticas y Bóveda Personal)
        # ---------------------------------------------------------
        # Esta tabla es la base para el cálculo de horas por juego
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS colecciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                id_usuario INT,
                id_juego INT,
                estado VARCHAR(50),
                horas_jugadas INT DEFAULT 0
            )
        """)
        
        # 4. Tabla de reseñas (Interacción social)
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
        print("✅ Configuración de Base de Datos finalizada exitosamente.")

    except Exception as e:
        print(f"❌ Error crítico en la inicialización de la DB: {str(e)}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

# Ejecución automática al levantar el servicio
crear_tablas_iniciales()

# Instancia principal de la aplicación
app = FastAPI(
    title="GameDex Pro Ultimate API",
    description="Backend completo para gestión de videojuegos, colecciones y estadísticas de usuario.",
    version="3.0.1"
)

# Configuración de Seguridad y Permisos (CORS)
# ---------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =================================================================
# --- MODELOS DE DATOS (SCHEMAS / PYDANTIC) ---
# =================================================================

class Videojuego(BaseModel):
    """Modelo para la creación de nuevos juegos en el catálogo."""
    titulo: str
    desarrollador: str
    precio: float = Field(..., ge=0, description="El precio no puede ser negativo")
    clasificacion: str
    generos: List[str]
    plataformas: List[str]
    imagen_url: Optional[str] = None

class UsuarioRegistro(BaseModel):
    """Modelo para el registro de nuevos usuarios."""
    username: str
    email: str
    password: str

class UsuarioLogin(BaseModel):
    """Modelo para la autenticación de usuarios."""
    email: str
    password: str

class ColeccionItem(BaseModel):
    """
    Modelo para gestionar la entrada a la colección.
    Incluye un limpiador para evitar errores de tipo desde el frontend.
    """
    id_juego: int
    estado: str 
    horas_jugadas: Any = 0

    @validator('horas_jugadas')
    def procesar_horas_entrada(cls, valor):
        """
        Limpia el dato recibido. Si el frontend manda un string vacío,
        un null o 'undefined', la API lo transforma en 0 automáticamente.
        """
        print(f"Validando horas de entrada: {valor}")
        try:
            if valor is None or valor == "" or valor == "undefined":
                return 0
            return int(valor)
        except (ValueError, TypeError):
            print(f"Advertencia: No se pudo convertir '{valor}' a entero. Usando 0.")
            return 0

class ResenaSchema(BaseModel):
    """Modelo para la publicación de reseñas."""
    id_usuario: Any 
    puntuacion: int = Field(..., ge=1, le=5)
    comentario: str

# =================================================================
# --- SECCIÓN: AUTENTICACIÓN Y USUARIOS ---
# =================================================================

@app.post("/api/v1/auth/registrar", tags=["Autenticación"])
def registrar_usuario(usuario: UsuarioRegistro):
    """
    Crea un nuevo registro de usuario en la base de datos.
    """
    print(f"Intentando registrar usuario: {usuario.username}")
    try:
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        consulta_sql = """
            INSERT INTO usuarios (username, email, password) 
            VALUES (%s, %s, %s)
        """
        datos_usuario = (usuario.username, usuario.email, usuario.password)
        
        cursor.execute(consulta_sql, datos_usuario)
        conexion.commit()
        
        print(f"Usuario {usuario.username} creado con ID {cursor.lastrowid}")
        return {
            "id_usuario": cursor.lastrowid, 
            "mensaje": "Cuenta creada satisfactoriamente"
        }
    except Exception as e:
        print(f"Error en registro: {str(e)}")
        raise HTTPException(status_code=400, detail="El email o nombre de usuario ya está en uso.")
    finally:
        if 'conexion' in locals(): conexion.close()

@app.post("/api/v1/auth/login", tags=["Autenticación"])
def login(credenciales: UsuarioLogin):
    """
    Verifica las credenciales y permite el acceso al sistema.
    """
    print(f"Petición de login para: {credenciales.email}")
    try:
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        consulta_sql = """
            SELECT id, username, email 
            FROM usuarios 
            WHERE email = %s AND password = %s
        """
        cursor.execute(consulta_sql, (credenciales.email, credenciales.password))
        usuario_encontrado = cursor.fetchone()
        
        if usuario_encontrado:
            print(f"Login exitoso para usuario ID: {usuario_encontrado[0]}")
            return {
                "mensaje": "Bienvenido al sistema",
                "usuario": {
                    "id": usuario_encontrado[0], 
                    "username": usuario_encontrado[1], 
                    "email": usuario_encontrado[2]
                }
            }
        else:
            print("Credenciales inválidas intentadas.")
            raise HTTPException(status_code=401, detail="Correo electrónico o contraseña incorrectos.")
    finally:
        if 'conexion' in locals(): conexion.close()

# =================================================================
# --- SECCIÓN: CATÁLOGO DE JUEGOS ---
# =================================================================

@app.get("/api/v1/juegos", tags=["Cliente"])
def listar_juegos_disponibles(genero: Optional[str] = Query(None)):
    """
    Obtiene la lista completa de videojuegos o filtra por género.
    """
    try:
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        if genero:
            print(f"Filtrando catálogo por género: {genero}")
            consulta_sql = "SELECT * FROM juegos WHERE JSON_CONTAINS(generos, %s)"
            cursor.execute(consulta_sql, (json.dumps(genero),))
        else:
            print("Obteniendo catálogo completo de juegos.")
            consulta_sql = "SELECT * FROM juegos"
            cursor.execute(consulta_sql)
        
        columnas = [columna[0] for columna in cursor.description]
        resultados = cursor.fetchall()
        
        lista_juegos = []
        for fila in resultados:
            lista_juegos.append(dict(zip(columnas, fila)))
            
        return {
            "total_encontrados": len(lista_juegos), 
            "datos": lista_juegos
        }
    finally:
        if 'conexion' in locals(): conexion.close()

# =================================================================
# --- SECCIÓN: GESTIÓN DE COLECCIÓN PERSONAL ---
# =================================================================

@app.get("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def ver_coleccion_completa(id_user: Any):
    """
    Obtiene todos los juegos que el usuario tiene guardados en su bóveda.
    """
    try:
        u_id = int(id_user)
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        # Unimos la tabla colecciones con juegos para traer los títulos
        consulta_sql = """
            SELECT j.id, j.titulo, c.estado, c.horas_jugadas
            FROM colecciones c
            JOIN juegos j ON c.id_juego = j.id
            WHERE c.id_usuario = %s
        """
        cursor.execute(consulta_sql, (u_id,))
        
        columnas = [col[0] for col in cursor.description]
        datos = [dict(zip(columnas, f)) for f in cursor.fetchall()]
        
        return {
            "usuario_id": u_id,
            "total_juegos": len(datos),
            "juegos": datos
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error al obtener la colección.")
    finally:
        if 'conexion' in locals(): conexion.close()

@app.post("/api/v1/usuarios/{id_user}/coleccion", tags=["Cliente"])
def gestionar_juego_en_coleccion(id_user: Any, item: ColeccionItem):
    """
    Añade o actualiza el progreso de un juego en la colección de un usuario.
    Esta ruta es inteligente: si el juego ya existe, actualiza las horas.
    """
    print(f"--- LOG OPERACIÓN COLECCIÓN ---")
    print(f"Usuario: {id_user} | Juego: {item.id_juego} | Horas: {item.horas_jugadas}")
    
    try:
        # Intento de conversión de ID para detectar 'undefined'
        try:
            id_usuario_limpio = int(id_user)
        except:
            print(f"ERROR: Se recibió ID de usuario inválido: {id_user}")
            raise HTTPException(status_code=400, detail="ID de usuario inválido. Verifique su sesión.")

        conexion = database.obtener_conexion()
        cursor = conexion.cursor()

        # Paso 1: Verificar si el juego ya está en la colección del usuario
        verificar_sql = "SELECT id FROM colecciones WHERE id_usuario = %s AND id_juego = %s"
        cursor.execute(verificar_sql, (id_usuario_limpio, item.id_juego))
        registro_existente = cursor.fetchone()

        if registro_existente:
            # Paso 2A: Actualizar registro existente
            print("El juego ya existe en la colección. Actualizando datos...")
            actualizar_sql = """
                UPDATE colecciones 
                SET estado = %s, horas_jugadas = %s 
                WHERE id_usuario = %s AND id_juego = %s
            """
            cursor.execute(actualizar_sql, (item.estado, item.horas_jugadas, id_usuario_limpio, item.id_juego))
            mensaje_final = "Progreso del juego actualizado con éxito."
        else:
            # Paso 2B: Crear nuevo registro
            print("El juego no estaba en la colección. Insertando nuevo registro...")
            insertar_sql = """
                INSERT INTO colecciones (id_usuario, id_juego, estado, horas_jugadas) 
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insertar_sql, (id_usuario_limpio, item.id_juego, item.estado, item.horas_jugadas))
            mensaje_final = "Juego añadido a la colección personal."
        
        conexion.commit()
        print("Operación completada exitosamente.")
        return {"mensaje": mensaje_final}
        
    except Exception as e:
        print(f"Error procesando colección: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno al guardar en la colección.")
    finally:
        if 'conexion' in locals(): conexion.close()

# =================================================================
# --- SECCIÓN: SISTEMA DE ESTADÍSTICAS ---
# =================================================================

@app.get("/api/v1/usuarios/{id_user}/stats", tags=["Estadísticas"])
def obtener_resumen_estadistico_global(id_user: Any):
    """
    Calcula estadísticas acumuladas de toda la cuenta del usuario.
    """
    print(f"Calculando estadísticas globales para usuario: {id_user}")
    try:
        user_id = int(id_user)
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        consulta_sql = """
            SELECT COALESCE(SUM(horas_jugadas), 0), COUNT(*) 
            FROM colecciones 
            WHERE id_usuario = %s
        """
        cursor.execute(consulta_sql, (user_id,))
        resultado = cursor.fetchone()
        
        # Lógica de rango basada en horas
        horas_totales = int(resultado[0])
        rango_usuario = "Novato"
        if horas_totales > 100: rango_usuario = "Veterano"
        if horas_totales > 500: rango_usuario = "Leyenda Gamer"

        return {
            "id_usuario": user_id, 
            "horas_acumuladas": horas_totales, 
            "total_juegos": resultado[1],
            "rango_actual": rango_usuario
        }
    except:
        return {"error": "No se pudieron obtener las estadísticas."}
    finally:
        if 'conexion' in locals(): conexion.close()

@app.get("/api/v1/usuarios/{id_user}/juego/{id_juego}/stats", tags=["Estadísticas"])
def obtener_estadistica_por_juego(id_user: Any, id_juego: Any):
    """
    Busca específicamente cuánto tiempo lleva el usuario en UN juego puntual.
    Ideal para mostrar en la página de detalles del juego.
    """
    print(f"Consultando stats de Juego ID {id_juego} para Usuario ID {id_user}")
    try:
        u_id = int(id_user)
        j_id = int(id_juego)
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        consulta_sql = """
            SELECT estado, horas_jugadas 
            FROM colecciones 
            WHERE id_usuario = %s AND id_juego = %s
        """
        cursor.execute(consulta_sql, (u_id, j_id))
        registro = cursor.fetchone()
        
        if registro:
            return {
                "id_juego": j_id, 
                "estado_actual": registro[0], 
                "horas_dedicadas": registro[1]
            }
        else:
            return {
                "id_juego": j_id, 
                "estado_actual": "No registrado", 
                "horas_dedicadas": 0
            }
    except Exception as e:
        print(f"Error en stats puntuales: {str(e)}")
        raise HTTPException(status_code=400, detail="Error al consultar datos del juego.")
    finally:
        if 'conexion' in locals(): conexion.close()

# =================================================================
# --- SECCIÓN: RESEÑAS Y FEEDBACK ---
# =================================================================

@app.post("/api/v1/juegos/{id_juego}/resenas", tags=["Reseñas"])
def publicar_nueva_resena(id_juego: int, resena: ResenaSchema):
    """
    Permite a los usuarios dejar sus opiniones sobre los juegos.
    """
    print(f"Nueva reseña para juego {id_juego}")
    try:
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        # Validar existencia del usuario/juego antes
        consulta_sql = """
            INSERT INTO resenas (id_juego, id_usuario, puntuacion, comentario) 
            VALUES (%s, %s, %s, %s)
        """
        datos = (id_juego, int(resena.id_usuario), resena.puntuacion, resena.comentario)
        
        cursor.execute(consulta_sql, datos)
        conexion.commit()
        
        return {"mensaje": "Reseña publicada exitosamente en la comunidad."}
    finally:
        if 'conexion' in locals(): conexion.close()

@app.get("/api/v1/juegos/{id_juego}/resenas", tags=["Reseñas"])
def ver_resenas_del_juego(id_juego: int):
    """
    Obtiene todas las reseñas de un título específico.
    """
    try:
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        consulta_sql = "SELECT * FROM resenas WHERE id_juego = %s"
        cursor.execute(consulta_sql, (id_juego,))
        
        columnas = [col[0] for col in cursor.description]
        datos = [dict(zip(columnas, f)) for f in cursor.fetchall()]
        
        return datos
    finally:
        if 'conexion' in locals(): conexion.close()

# =================================================================
# --- SECCIÓN: ADMINISTRACIÓN DEL SISTEMA ---
# =================================================================

@app.post("/api/v1/admin/juegos", tags=["Admin"])
def dar_de_alta_juego(juego: Videojuego, x_token: str = Header(None)):
    """
    Permite a los administradores agregar nuevos títulos al catálogo global.
    """
    if x_token != "secret-admin-key":
        print("INTENTO DE ACCESO NO AUTORIZADO A ADMIN")
        raise HTTPException(status_code=403, detail="Token de administrador inválido.")
    
    try:
        print(f"Admin registrando nuevo juego: {juego.titulo}")
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        consulta_sql = """
            INSERT INTO juegos (titulo, desarrollador, precio, clasificacion, imagen_url, generos, plataformas) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        valores = (
            juego.titulo, juego.desarrollador, juego.precio, 
            juego.clasificacion, juego.imagen_url, 
            json.dumps(juego.generos), json.dumps(juego.plataformas)
        )
        
        cursor.execute(consulta_sql, valores)
        conexion.commit()
        
        return {
            "id_juego": cursor.lastrowid, 
            "mensaje": "El juego ha sido añadido al catálogo global."
        }
    finally:
        if 'conexion' in locals(): conexion.close()

@app.delete("/api/v1/admin/juegos/{id_juego}", tags=["Admin"])
def eliminar_juego_catalogo(id_juego: int, x_token: str = Header(None)):
    """
    Elimina un juego del sistema de forma permanente.
    """
    if x_token != "secret-admin-key":
        raise HTTPException(status_code=403, detail="Permisos denegados.")
    try:
        conexion = database.obtener_conexion()
        cursor = conexion.cursor()
        
        cursor.execute("DELETE FROM juegos WHERE id = %s", (id_juego,))
        conexion.commit()
        
        return {"mensaje": f"Juego con ID {id_juego} ha sido eliminado."}
    finally:
        if 'conexion' in locals(): conexion.close()