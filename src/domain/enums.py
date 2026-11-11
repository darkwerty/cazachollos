from enum import Enum


class CategoryEnum(str, Enum):
    TECNOLOGIA = "tecnologia"
    VIDEOJUEGOS = "videojuegos"
    HOGAR = "hogar"
    COCINA = "cocina"
    BRICOLAJE = "bricolaje"
    MODA = "moda"
    BELLEZA = "belleza"
    DEPORTE = "deporte"
    JUGUETES = "juguetes"
    ALIMENTACION = "alimentacion"
    MASCOTAS = "mascotas"
    LIBROS = "libros"
    OFICINA = "oficina"
    MOTOR = "motor"
    OTROS = "otros"


# Visible names (web and bot)
CATEGORY_LABELS = {
    "tecnologia": "Tecnología",
    "videojuegos": "Videojuegos",
    "hogar": "Hogar",
    "cocina": "Cocina",
    "bricolaje": "Bricolaje y jardín",
    "moda": "Moda",
    "belleza": "Belleza y salud",
    "deporte": "Deporte",
    "juguetes": "Juguetes y bebé",
    "alimentacion": "Alimentación",
    "mascotas": "Mascotas",
    "libros": "Libros, música y cine",
    "oficina": "Oficina y papelería",
    "motor": "Motor",
    "otros": "Otros",
}
