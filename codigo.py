import os
print(f"Cores disponibles: {os.cpu_count()}")

# Usa: os.cpu_count() - 1 (deja uno libre para el sistema)