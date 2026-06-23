import urllib.request
import json
import random
from pathlib import Path

# URLs de descarga de E-14 por departamento
# Formato: https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf/{depto}/{muni}/{zona}/{puesto}/{mesa}/PRE/E14-{mesa}.pdf
# Usamos endpoint de API para obtener códigos válidos del departamento

def get_departamentos_api():
    """Obtener lista de departamentos de la API de Registraduría."""
    try:
        req = urllib.request.Request("https://divulgacione14presidente.registraduria.gov.co/api/department")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error API departamentos: {e}")
        return []

def generar_url_pdf(cod_depto, cod_muni, cod_zona, cod_puesto, mesa):
    base = "https://divulgacione14presidente.registraduria.gov.co/assets/temis/pdf"
    return f"{base}/{cod_depto}/{cod_muni}/{cod_zona}/{cod_puesto}/{'{:03d}'.format(mesa)}/PRE/E14-{'{:03d}'.format(mesa)}.pdf"

# Códigos predefinidos para los departamentos objetivo
# Basado en estructura de la Registraduría
departamentos = {
    "Atlántico": "08",
    "Nariño": "52",
    "Chocó": "27",
    "Bogotá D.C.": "11",
}

print("Departamentos objetivo:")
for nombre, cod in departamentos.items():
    print(f"  {nombre}: {cod}")
    
