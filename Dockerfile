FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11

# Copiamos el archivo de requisitos al contenedor
COPY ./requirements.txt /app/requirements.txt

# Instalamos las librerías (mysql-connector y pydantic)
RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

# Copiamos todo el código de tu carpeta al contenedor
COPY . /app