using 'main.bicep'

// Variables de entorno al desplegar (ver README):
//   IMAGE: meaculpaacrl5bhzhsghjggc.azurecr.io/cazachollos:<sha>
//   PG_PASSWORD: contraseña de PostgreSQL (se genera una vez y se guarda fuera del repositorio)
//   AUTH_CLIENT_ID, AUTH_CLIENT_SECRET, AUTH_ALLOWED_OBJECT_ID: login del panel (vacíos en el primer despliegue)
param image = readEnvironmentVariable('IMAGE')
param acrName = 'meaculpaacrl5bhzhsghjggc'
param openAiAccountName = 'meaculpa-fc-7952'
param pgPassword = readEnvironmentVariable('PG_PASSWORD')
param authClientId = readEnvironmentVariable('AUTH_CLIENT_ID', '')
param authClientSecret = readEnvironmentVariable('AUTH_CLIENT_SECRET', '')
param authAllowedObjectIds = empty(readEnvironmentVariable('AUTH_ALLOWED_OBJECT_ID', '')) ? [] : [readEnvironmentVariable('AUTH_ALLOWED_OBJECT_ID', '')]

// Canales públicos (tienen vista web en t.me/s/<canal>). ninjachat es un grupo y linkscrewfinds no muestra
// mensajes en la vista web: sin cuenta de Telegram no se pueden leer.
param channels = 'canaldechollos,canaldescuentos,canalninja,chollo100x100,DonOFERTON_oficial,zchollos,hacooesp,BricoGangas,Baratisimo,chollacos,EnlacesyMarcasHacoo'

param budgetAmount = 5
param budgetEmails = [
  'dani.algar02@gmail.com'
]
