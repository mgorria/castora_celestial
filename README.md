# Control Castora

Sistema de bots de Telegram para una narrativa personal.

El proyecto ejecuta varios bots en el mismo proceso:

- **Oficina Castori**, el bot visible para Sandra.
- **Mimosuga**, una tortuguita muy mayor y entrañable, figura de abuela para Sandra.
- **Corte de Pompones y Plumas**, tribunal carinoso para juicios de broma.
- **Doctor Salchicher**, consultorio de cuidados cotidianos y mimos.
- **Centralita Magica**, el bot privado desde el que se envian mensajes y se reciben respuestas.

La estructura esta preparada para anadir mas animales en el futuro mediante el diccionario `ANIMALS` de `main.py`.

## Requisitos

- Python 3.11 o superior.
- Tokens de BotFather:
  - `TOKEN_CASTORI`
  - `TOKEN_MIMOSUGA`
  - `TOKEN_CORTE`
  - `TOKEN_CENTRALITA`
- Tu chat id personal de Telegram:
  - `MI_CHAT_ID`
  - `CASTORI_CHAT_ID` si ya se conoce el chat id de Sandra.
  - `MIMOSUGA_CHAT_ID` si ya se conoce el chat id de Sandra para Mimosuga.
  - `CORTE_CHAT_ID` si ya se conoce el chat id de Sandra para la Corte.

## Configuracion local

Crea un archivo `.env` en la raiz del proyecto con este contenido:

```env
TOKEN_CASTORI=token_real_de_oficina_castori
TOKEN_MIMOSUGA=token_real_de_mimosuga
TOKEN_CORTE=token_real_de_corte
TOKEN_CENTRALITA=token_real_de_centralita_magica
MI_CHAT_ID=tu_chat_id
CASTORI_CHAT_ID=
MIMOSUGA_CHAT_ID=
CORTE_CHAT_ID=
LOG_LEVEL=INFO
DATA_FILE=data.json
MAX_HISTORY_PER_ANIMAL=50
```

Instala dependencias:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Arranca el sistema:

```powershell
.\start.ps1
```

## Uso

Primero Sandra debe abrir el bot **Oficina Castori** y enviar `/start`.

En ese momento el proyecto guarda automaticamente su `chat_id` en `data.json`.

Desde tu Telegram, abre **Centralita Magica** y usa:

```text
/status
/castori texto que quieres enviar
/mimosuga texto que quieres enviar
/corte texto que quieres enviar
/historial castori
/historial mimosuga
/historial castori 20
/acusar Patita cruzo el pasillo sin entregar beso reglamentario.
/alegar Niego los hechos y solicito atenuante por preparacion de cafe.
/caso_estado
/programar mimosuga lunes 09:00 Que tengas buena semana, patita.
/programar mimosuga 21/06/2026 16:00 Tengo algo que contarte, sol mio.
/programados
/cancelar id_de_programacion
/pausar_programas
/reanudar_programas
/status
```

Las respuestas que Sandra envie a Oficina Castori se copiaran automaticamente a tu chat privado con Centralita.
El historial guarda los ultimos mensajes de cada animal en `data.json`.
Los mensajes programados pueden ser semanales o de una fecha exacta, se revisan periodicamente y se envian en la zona horaria configurada.
Si algo raro ocurre, `/pausar_programas` detiene los envios programados hasta usar `/reanudar_programas`.
`/status` muestra el estado general: bots vinculados, Railway/worker, base de datos,
OpenAI, programaciones, respuestas suaves de Mimosuga, cuentos y comandos utiles.

## Cuentos y lore

Mimosuga puede ofrecer un cuento diario con:

```text
/cuento
/cuento historia de Caparantonio
/cuento algo sobre una carta antigua
```

El flujo es:

1. Mimosuga comprueba si Patita ya recibio cuento hoy.
2. Si no lo recibio, genera dos opciones basadas en `lore/resumen-para-ia.md`.
   Si Patita escribe algo despues de `/cuento`, lo usa como tema orientativo.
3. Patita elige una opcion con botones.
4. Mimosuga genera y envia el cuento completo.
5. Solo despues de enviarlo se consume el limite diario.
6. La historia queda guardada en PostgreSQL con estado `pending`.

Comandos privados de administrador en **Centralita Magica**:

```text
/admin_ultimos
/admin_ver ID
/admin_aprobar ID
/admin_descartar ID
/admin_canon ID
/admin_lore
/admin_memoria_cuentos
/admin_cuento_prueba mimosuga
/mimosuga_auto status
/mimosuga_auto on
/mimosuga_auto auto
/mimosuga_auto revision
/mimosuga_auto off
```

El lore editable vive en:

```text
lore/resumen-para-ia.md
lore/continuidad-canonica.md
lore/reglas-de-tono.md
lore/personajes/
lore/historias/
```

`lore/continuidad-canonica.md` sirve para fijar hechos que solo deben ocurrir una vez,
como el primer encuentro de Mimosuga y Caparantonio. Cuando una historia de origen te
guste, resume ahi la version canonica para que futuras historias no la contradigan.

## Respuestas suaves de Mimosuga

Mimosuga puede preparar borradores automaticos de respuesta cuando Patita le escriba.
Puede funcionar en modo revision o en modo automatico. En modo revision, el administrador
recibe la propuesta en **Centralita Magica** y decide con botones si la envia o la descarta.
En modo automatico, Mimosuga envia sola las respuestas que la IA considera charla ligera;
si el mensaje parece delicado, importante o ambiguo, avisa al administrador y no envia nada.

Comandos privados:

```text
/mimosuga_auto on
/mimosuga_auto auto
/mimosuga_auto revision
/mimosuga_auto off
/mimosuga_auto status
```

`/mimosuga_auto on` activa el modo revision. Para activar envio automatico hay que usar
explicitamente `/mimosuga_auto auto`.

Cuando esta encendido, cada mensaje textual que llegue a Mimosuga genera una propuesta
breve si la IA lo considera una charla ligera. Para que no responda frase por frase,
el bot espera unos segundos antes de redactar: si Patita envia varios mensajes seguidos,
los agrupa y prepara una sola respuesta para todo el bloque. Si el mensaje parece delicado
o no trivial, la Centralita avisa al administrador y no propone una respuesta automatica.

La espera de agrupacion se puede ajustar con:

```env
AUTO_REPLY_IDLE_SECONDS=90
```

## Corte de Pompones y Plumas

La Corte permite abrir juicios de broma desde **Centralita Magica**:

```text
/acusar Patita cruzo el pasillo sin entregar beso reglamentario.
```

Patita recibe una acusacion formal desde el bot de la Corte. Sus alegaciones se agrupan
durante `AUTO_REPLY_IDLE_SECONDS` segundos, igual que Mimosuga, y la IA responde como juez.
Si ya hay suficientes alegaciones, dicta sentencia con condenas carinosas: abrazos, besos
reglamentarios, sofa, modo amor o indemnizacion de mimos.

Patita tambien puede iniciar una causa desde el propio bot de la Corte:

```text
/acusar Miguel ha cometido abandono de abrazo reglamentario.
```

Cuando Patita abre causa, Control Castori avisa al administrador y permite responder con:

```text
/alegar <texto>
```

Si Patita escribe en la Corte sin causa abierta, el bot solo informa de que no hay proceso
abierto y le indica que use `/acusar` para presentar denuncia.

La Corte consulta normativa editable en:

```text
lore/corte/codigo-penal-infracciones-pata.md
lore/corte/codigo-penal-infracciones-oso.md
lore/corte/jurisprudencia.md
lore/corte/jueces.md
```

Tambien consulta automaticamente las ultimas sentencias guardadas en PostgreSQL como
jurisprudencia reciente. Si un articulo o precedente encaja, la IA puede citarlo en la
sentencia.

Cada causa elige automaticamente un juez ponente desde `lore/corte/jueces.md`.
Los jueces tienen criterios distintos: algunos absuelven con facilidad, otros se fijan
mas en fugas de abrazo, otros rebajan por atenuantes o archivan por exceso de encanto.
Esto ayuda a que las sentencias no sean siempre "culpable con atenuantes".

Antes del fundamento y del fallo, el juez incluye una valoracion personal en primera
persona. Comenta los hechos y las alegaciones con su propio caracter, de modo que no solo
cambian el veredicto y la pena: tambien cambia la voz con la que se dicta la sentencia.

Tras una acusacion, la parte acusada recibe botones de estrategia de defensa:
negar hechos, alegar atenuantes, confesar parcialmente o solicitar acuerdo de sofa.
Al pulsar un boton, la Corte formula una pregunta de interrogatorio antes de recibir
las alegaciones libres.

Para consultar la ultima causa:

```text
/caso_estado
```

## Railway

### Doctor Salchicher

Bot: [Doctor Salchicher](https://t.me/DoctorSalchicher_bot).
Es un personaje de cuidados generales para una persona adulta. Hace una o dos
preguntas por turno y propone una receta de cuidados para molestias leves recientes.
No diagnostica, receta medicamentos ni aconseja suplementos como jalea real.
La IA selecciona preguntas y cuidados de un catalogo acotado, no envia consejos
medicos de texto libre. Esto limita su alcance; no es un sistema de triaje validado.

En el servicio **worker**, anadir:

```env
TOKEN_SALCHICHER=token_nuevo_de_BotFather
SALCHICHER_CHAT_ID=el_mismo_id_personal_de_Patita
SALCHICHER_IDLE_SECONDS=90
```

Reutiliza `OPENAI_API_KEY`, `OPENAI_MODEL` y el volumen `DATA_FILE` existentes.
Opcionalmente `SALCHICHER_MODEL` permite elegir otro modelo solo para este bot.
No requiere otra base de datos ni migraciones. Si falta el token, los otros bots
siguen funcionando. Solo permite chats privados del propietario y de Patita:
usa `SANDRA_TELEGRAM_ID`, o el chat conocido de Salchicher/Mimosuga/Castori.
No vincula al primer desconocido que le escriba.

Patita abre el enlace y pulsa **Iniciar**. `/start` solo notifica al administrador,
sin saludos automaticos. Al escribir o usar `/consulta`, elige consulta privada o
compartirla con el Oso. Luego cuenta lo que le pasa. Los mensajes se agrupan tras
90 segundos de silencio. El bot recuerda la consulta, pregunta lo que falte y da
cuidados sencillos cuando procede. Ante posible urgencia detectada por el filtro
local responde inmediatamente, incluso con el modo automatico apagado. El modelo
tambien revisa el contexto; los filtros no garantizan detectar todas las urgencias.

Control Castori:

```text
/status
/salchicher_auto on
/salchicher_auto off
/salchicher Un abrazo de consultorio, patita.
```

En el bot Salchicher: `/consulta`, `/ayuda` y `/olvidar`. El administrador puede
probarlo desde su propio chat con Salchicher, sin vincular su ID como el de Patita.
Si ella opta por compartir, Control recibe un resumen por respuesta con el bloque
de entrada y la respuesta completa. Si elige privado no se reenvian sus textos.

La memoria de consultas vive en `data.json` del volumen, separada del historial
general, cuentos y lore. Se elimina tras 48 horas sin mensajes (limpieza periodica
o al arrancar). `/olvidar` elimina esa memoria y cancela lo pendiente; no borra las
copias en Telegram ni los registros que el proveedor pudiera conservar. OpenAI
recibe los textos para responder con `store=False`; esto no equivale a una promesa
de retencion cero del proveedor. No se imprimen sintomas ni respuestas IA en logs.
Una consulta pendiente puede continuar tras reiniciar; no se reenvian respuestas
ya reservadas. Un envio con resultado incierto no se repite automaticamente.

Personalidad editable: `lore/personajes/doctor-salchicher.md`.
Catalogo y limites: `salchicher_service.py`. Vida de la consulta: `salchicher.py`.
Pruebas sin API, Telegram ni cobros: `python -m unittest discover -s tests -v`.

Fuentes para el catalogo (revisadas el 15/10/2026):

- [NHS: cuidados del resfriado](https://www.nhs.uk/conditions/common-cold/).
- [NHS: dificultad para respirar](https://www.nhs.uk/symptoms/shortness-of-breath/).
- [Comunidad de Madrid: urgencias y 112](https://www.comunidad.madrid/salud/atencion-urgencias-emergencias-sanitarias).
- [TGA: precauciones con jalea real](https://www.tga.gov.au/resources/advertising-permissions/royal-jelly).

### Vaca Mágica

La Vaca habla con Patita, guarda su lista de ilusiones y prepara mensajes para las
visitas sorpresa de diciembre. Tiene una voz cariñosa y traviesa, con expresiones
como «muuuuy» y «muuuucho». Apuntar un deseo nunca promete que vaya a recibirlo.

En el servicio **worker**, configurar:

```env
TOKEN_VACA=token_nuevo_de_BotFather
VACA_CHAT_ID=el_id_personal_de_Patita
VACA_IDLE_SECONDS=20
```

Reutiliza `OPENAI_API_KEY`, `OPENAI_MODEL`, `APP_TIMEZONE` (por defecto
`Europe/Madrid`) y el volumen `DATA_FILE`. `VACA_MODEL` permite elegir otro modelo
para la Vaca. No requiere otra base de datos ni migraciones. Si falta `TOKEN_VACA`,
este bot no se inicia y los demás siguen funcionando.

Patita debe abrir el bot y pulsar **Iniciar** antes de activar visitas. La vinculación
se limita a su identidad conocida: `SANDRA_TELEGRAM_ID`, el ID configurado de Vaca o
el chat conocido de Mimosuga/Castori. Solo se aceptan chats privados de Patita y del
propietario; no se vincula a un desconocido que escriba primero. Las pruebas del
propietario mantienen una lista independiente.

Patita puede decir «apúntame unas botas negras», corregir «mejor en talla 38», pedir
que quite algo o consultar sus deseos. Si comenta que algo le gusta sin pedirlo,
la Vaca pide aclaración antes de modificar la lista. La conversación se agrupa tras
`VACA_IDLE_SECONDS` segundos de silencio. También dispone de comandos directos:

```text
/ayuda
/lista
/pedir botas negras talla 38 https://ejemplo.com/botas
/quitar w1
/favorito w1
/olvidar
```

`/favorito` pone o retira la estrella. `/olvidar` borra la memoria de conversación y
cancela su respuesta pendiente, conservando la lista; no borra mensajes de Telegram.
La lista admite hasta 60 deseos y conserva los enlaces y preferencias que facilite
Patita. La ayuda explica que el Oso puede consultar esa lista para preparar sorpresas.

Desde el chat **privado** del propietario con Control Castori:

```text
/vaca_ayuda
/vaca_deseos
/vaca_auto on
/vaca_auto off
/vaca_auto status
/vaca Un abrazo de pezuñas, patita.
/vaca_visita 15/12/2026 08:30 | un libro de ilustraciones y unos calcetines suaves
```

`/vaca_visita` prepara un borrador privado con los regalos, fechas y los tres textos.
Por defecto hay una pista tres días antes a las 18:00, otra el día anterior a las
18:00 y el mensaje de la mañana a la hora indicada. Las pistas que ya hayan pasado
o caigan fuera de diciembre se omiten; una visita próxima puede tener solo el mensaje
de la mañana. La entrega y cualquier horario editado deben ser futuros y de diciembre.

Revisar el borrador y activarlo con su ID:

```text
/vaca_visitas
/vaca_visitas ID
/vaca_activar ID
```

Hasta activar, no se envía ningún mensaje de esa visita. La mañana presupone que el
propietario habrá colocado los regalos para la fecha planificada: el bot no verifica
una entrega física ni exige otra confirmación cada noche. El generador de pistas
recibe los regalos para redactar el borrador privado, que debe revisarse antes de
activarlo. La conversación de Patita no recibe los regalos ni las fechas pendientes.

Para ajustar una visita, los eventos se llaman `pista1`, `pista2` y `manana`:

```text
/vaca_texto ID pista1 | He encontrado una cinta con un secreto de pezuña.
/vaca_hora ID pista1 12/12/2026 19:00
/vaca_fecha ID 20/12/2026 08:30
/vaca_cancelar ID
/vaca_pausa on
/vaca_pausa off
```

Cambiar un texto o una hora devuelve la visita a borrador y requiere activarla de
nuevo. `/vaca_fecha` cambia la entrega y recalcula las pistas pendientes, conservando
los textos y lo ya enviado. Para mover la entrega a otro año se debe usar ese comando,
no `/vaca_hora`. Un mensaje enviado o de resultado incierto no se modifica ni reenvía.
La cancelación conserva ese historial. `/vaca_pausa` afecta a todas las visitas; la
pausa global `/pausar_programas` también impide sus envíos. `/vaca_auto` controla la
conversación, de forma independiente de las visitas. Usar `/vaca_visita` para estas
entregas: el comando genérico `/programar vaca` está deshabilitado.

Cada visita activa conserva el destinatario vinculado en ese momento. Si cambia,
vuelve a borrador para revisarla. Los mensajes vencidos hace más de dos horas caducan
y se avisa al propietario una sola vez. Se reserva cada envío antes de contactar con
Telegram; tras un timeout, error o reinicio ambiguo no se reintenta automáticamente.
Conviene comprobar el chat antes de decidir si hace falta otro mensaje.

Los deseos y la conversación viven en `data.json`, separados del registro privado
`vaca_campaigns`, que contiene regalos, fechas y borradores. No se incorpora ese
registro secreto al contexto de la IA conversacional, al lore general ni al historial
de Patita. Los comandos de gestión se limitan al propietario en chat privado y los
errores no imprimen regalos ni respuestas completas en logs. Los datos permanecen
en el volumen: la separación de contexto no cifra el archivo. Las llamadas a OpenAI
usan `store=False`, sin prometer retención cero por parte del proveedor.

Personalidad: `lore/personajes/vaca-magica.md`. IA y validación de operaciones:
`vaca_service.py`. Conversación y deseos: `vaca.py`. Visitas: `vaca_campaigns.py`.
La respuesta estructurada sigue la documentación de
[Structured Outputs de OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

Pruebas con servicios simulados, sin mensajes reales ni llamadas a la API:
`python -m unittest discover -s tests -v`. Cubren deseos, permisos, aislamiento de
secretos, fechas Madrid/UTC, borradores, cancelación, reprogramación, caducidad y
resultados de envío inciertos.

### Despliegue general

En Railway, conecta el repositorio de GitHub y configura estas variables:

```env
TOKEN_CASTORI=token_real_de_oficina_castori
TOKEN_MIMOSUGA=token_real_de_mimosuga
TOKEN_CORTE=token_real_de_corte
TOKEN_CENTRALITA=token_real_de_centralita_magica
MI_CHAT_ID=tu_chat_id
CASTORI_CHAT_ID=chat_id_de_sandra
MIMOSUGA_CHAT_ID=chat_id_de_sandra_para_mimosuga
CORTE_CHAT_ID=chat_id_de_sandra_para_corte
LOG_LEVEL=INFO
DATA_FILE=data.json
MAX_HISTORY_PER_ANIMAL=50
APP_TIMEZONE=Europe/Madrid
SCHEDULER_POLL_SECONDS=30
STARTUP_DELAY_SECONDS=8
AUTO_REPLY_IDLE_SECONDS=90
DATABASE_URL=postgresql://...
OPENAI_API_KEY=tu_api_key_openai
OPENAI_MODEL=gpt-5.5
TELEGRAM_ADMIN_ID=tu_chat_id
SANDRA_TELEGRAM_ID=chat_id_de_sandra
PENDING_STORIES_DIR=/app/data/lore/historias/pendientes
RECENT_STORY_MEMORY_PATH=/app/data/lore/historias/memoria-reciente.md
```

Si `CASTORI_CHAT_ID` esta configurado, el bot lo usara directamente aunque `data.json` no exista todavia en Railway.

Para persistencia en Railway, crea un Volume montado en `/app/data` y configura:

```env
DATA_FILE=/app/data/data.json
```

Si Railway expone `RAILWAY_VOLUME_MOUNT_PATH`, el bot tambien puede usar automaticamente `data.json` dentro del volumen.

Railway usara el `Procfile`:

```Procfile
worker: python main.py
```

Al arrancar, el bot crea automaticamente las tablas necesarias si `DATABASE_URL` esta configurada:

- `users`
- `stories`
- `daily_limits`
- `story_offers`
- `auto_reply_drafts`
- `court_cases`
- `court_messages`

## Nota de seguridad

No subas nunca el archivo `.env` ni `data.json` al repositorio. Ya estan incluidos en `.gitignore`.
