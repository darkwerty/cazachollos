using 'main.bicep'

// Variables de entorno al desplegar (ver README):
//   IMAGE: meaculpaacrl5bhzhsghjggc.azurecr.io/cazachollos:<sha>
//   PG_PASSWORD: contraseña de PostgreSQL (se genera una vez y se guarda fuera del repositorio)
//   GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET: cliente OAuth web de Google para el login del panel (vacíos: sin publicar)
param image = readEnvironmentVariable('IMAGE')
param acrName = 'meaculpaacrl5bhzhsghjggc'
param openAiAccountName = 'meaculpa-fc-7952'
param pgPassword = readEnvironmentVariable('PG_PASSWORD')
param googleClientId = readEnvironmentVariable('GOOGLE_CLIENT_ID', '')
param googleClientSecret = readEnvironmentVariable('GOOGLE_CLIENT_SECRET', '')
param allowedEmails = 'dani.algar02@gmail.com'
param botToken = readEnvironmentVariable('BOT_TOKEN', '')
param webhookSecret = readEnvironmentVariable('TELEGRAM_WEBHOOK_SECRET', '')
param telegramBotUsername = 'qwertychollos_bot'
param portfolioGoogleClientId = '180969024310-scukcmroa2k7brbfq3m3q573qdsakqk2.apps.googleusercontent.com'

// Canales públicos (tienen vista web en t.me/s/<canal>). ninjachat es un grupo y linkscrewfinds no muestra
// mensajes en la vista web: sin cuenta de Telegram no se pueden leer.
param channels = 'canaldechollos,canaldescuentos,canalninja,chollo100x100,DonOFERTON_oficial,zchollos,hacooesp,BricoGangas,Baratisimo,chollacos,EnlacesyMarcasHacoo'

param budgetAmount = 5
param budgetEmails = [
  'dani.algar02@gmail.com'
]
