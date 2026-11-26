# riot-cleaner

Limpia tu lista de amigos de Riot Games (VALORANT / League of Legends) eliminando a los contactos que llevan mucho tiempo sin conectarse.

Usa la **API local del Riot Client** (la misma que usa el cliente, en `127.0.0.1`). No pide tu contraseña, no usa servicios externos y no requiere dependencias: solo Python 3.9+.

## Cómo funciona

1. Lee tu lista de amigos y la fecha de última conexión (`last_online_ts`) de cada uno.
2. Clasifica a cada amigo:

   | Estado | Significado |
   |---|---|
   | **candidato** | Más de `--days` días sin conectarse (365 por defecto) o sin fecha registrada. |
   | **activo** | Se conectó hace poco, está conectado ahora o aparece en los logs recientes de VALORANT. |
   | **protegido** | Inactivo, pero tiene nota (`--keep-notes`) o está en un grupo protegido (`--keep-group`). |
   | **conservado** | Candidato que tú sacaste de `candidatos.csv` o marcaste con `no`. |

3. Genera `candidatos.csv` y un `dashboard.html` interactivo para revisar la selección.
4. Solo elimina con `--apply`, y únicamente a quienes estén marcados `si` en el CSV.

### Sobre "sin dato"

Riot solo devuelve la fecha de última conexión de forma reciente. Un amigo sin fecha **puede ser una cuenta abandonada o alguien que oculta su estado**. Por eso el script revisa los logs locales de VALORANT (`%LOCALAPPDATA%\VALORANT\Saved\Logs`) y marca como activo a quien aparezca en ellos. Esos logs solo cubren los últimos días, así que **revisa siempre la lista antes de eliminar**.

## Uso

Requisitos: Windows, el Riot Client abierto y con sesión iniciada.

```powershell
# 1. Simulación: genera candidatos.csv, dashboard.html y una copia de seguridad. No borra nada.
python riot_friends_cleaner.py --keep-notes --keep-group "Mi grupo"

# 2. Revisa la selección:
#    - abre dashboard.html, desmarca a quien quieras conservar y pulsa "Exportar selección", o
#    - edita candidatos.csv: pon "no" en la columna "eliminar" o borra la fila.

# 3. Vuelve a ejecutar la simulación para ver tu selección reflejada en el dashboard (opcional).

# 4. Elimina
python riot_friends_cleaner.py --apply
python riot_friends_cleaner.py --apply --csv "C:\Users\tu_usuario\Downloads\candidatos.csv"
```

### Opciones

| Opción | Descripción |
|---|---|
| `--days N` | Días de inactividad mínimos para ser candidato (por defecto 365). |
| `--keep-notes` | No eliminar a amigos con nota. |
| `--keep-group G` | No eliminar a amigos del grupo `G` (se puede repetir). |
| `--no-null` | No considerar candidatos a quienes no tienen fecha de última conexión. |
| `--apply` | Elimina a los marcados `si` en el CSV. |
| `--csv RUTA` | CSV a usar con `--apply` (por defecto `candidatos.csv`). |
| `--reset` | Ignora la selección guardada en `candidatos.csv` y la genera desde cero. |

## Seguridad y privacidad

- **Eliminar no se puede deshacer**: tendrías que volver a enviar la solicitud de amistad. Cada simulación guarda tu lista completa en `backups/amigos-AAAAMMDD-HHMMSS.json`.
- Las ejecuciones con `--apply` respetan tu selección: nunca eliminan a alguien que no esté marcado `si`, y saltan a quien ya no está en la lista (así puedes reintentar sin riesgo).
- `backups/`, `candidatos.csv` y `dashboard.html` contienen datos de tus amigos y están en `.gitignore`. No los publiques.
- El script usa el certificado autofirmado del cliente local y la contraseña temporal de su `lockfile`. Nada sale de tu PC salvo las peticiones que el propio Riot Client hace a Riot al eliminar.

## Detalles técnicos

- Credenciales: `%LOCALAPPDATA%\Riot Games\Riot Client\Config\lockfile` (`nombre:pid:puerto:contraseña:protocolo`).
- Listar amigos: `GET /chat/v4/friends`.
- Eliminar: `DELETE /chat/v4/friends` con el cuerpo `{"pid": "..."}`. Con algunos amigos de otras regiones, borrar por `{"puuid": "..."}` responde OK pero no tiene efecto; por eso el script usa `pid`.

## Archivos

| Archivo | Descripción |
|---|---|
| `riot_friends_cleaner.py` | Script principal (CLI). |
| `dashboard_template.html` | Plantilla del dashboard; el script inyecta los datos y genera `dashboard.html`. |

*Proyecto no oficial, sin relación con Riot Games.*
