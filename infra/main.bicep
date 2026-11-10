// CazaChollos en Azure: lee canales públicos de Telegram cada 15 minutos (7:00 a 24:00, hora de Madrid), guarda
// las ofertas en PostgreSQL y las enseña en un panel protegido con inicio de sesión.
//
// Despliega en su propio grupo de recursos:
//   - Log Analytics (con tope diario) y un entorno de Container Apps (plan Consumption, sin coste fijo)
//   - Identidad administrada asignada por el usuario, con AcrPull sobre el Container Registry de Mea culpa y
//     Cognitive Services OpenAI User sobre su cuenta de Foundry (roles.bicep): sin claves y sin costes fijos nuevos
//   - Azure Database for PostgreSQL Flexible Server B1ms (750 h gratis al mes los 12 primeros meses de la cuenta)
//   - Container Apps Job programado: una pasada por los canales y termina (no se queda encendido)
//   - Container App del panel (Streamlit), que escala a cero, con el login integrado de Container Apps (Google)
//     y una lista de correos que pueden entrar (ALLOWED_EMAILS)
//   - Presupuesto mensual con alertas por correo
//
// Uso (ver README): az acr build ... y después
//   az deployment group create -g rg-cazachollos -f infra/main.bicep -p infra/main.bicepparam
targetScope = 'resourceGroup'

@description('Prefijo corto para nombrar recursos')
param prefix string = 'cazachollos'

param location string = resourceGroup().location

@description('Imagen de la aplicación, en el Container Registry de Mea culpa')
param image string

@description('Container Registry y cuenta de Foundry que se reutilizan (grupo de Mea culpa)')
param sharedResourceGroup string = 'rg-mea-culpa'
param acrName string
param openAiAccountName string
@description('Deployment de Azure OpenAI para la extracción')
param openAiDeployment string = 'gpt-4.1-nano'

@description('Canales públicos de Telegram, separados por comas')
param channels string

@description('Cada cuánto se pasa (cron en UTC). 5-23 UTC cubre de 7:00 a 24:00 en Madrid en invierno y en verano; fuera de ACTIVE_HOURS la pasada termina sin hacer nada')
param cron string = '*/15 5-23 * * *'
param activeHours string = '7-24'
@description('Tope de llamadas a la IA al día')
param llmMaxCallsPerDay int = 400

@description('Contraseña del administrador de PostgreSQL')
@secure()
param pgPassword string
param pgUser string = 'cazachollos'

@description('Login del panel con Google (cliente OAuth web). Vacío: el panel no se publica en Internet')
param googleClientId string = ''
@secure()
param googleClientSecret string = ''
@description('Correos que pueden entrar en el panel, separados por comas (Google deja entrar a cualquier cuenta)')
param allowedEmails string

param budgetAmount int = 5
param budgetStartDate string = utcNow('yyyy-MM-01')
param budgetEmails array

var suffix = uniqueString(resourceGroup().id)
var withAuth = !empty(googleClientId)

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: 1 }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${prefix}-id-${suffix}'
  location: location
}

module roles 'roles.bicep' = {
  name: '${prefix}-roles'
  scope: resourceGroup(sharedResourceGroup)
  params: {
    principalId: identity.properties.principalId
    acrName: acrName
    openAiAccountName: openAiAccountName
  }
}

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: '${prefix}-pg-${suffix}'
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: pgUser
    administratorLoginPassword: pgPassword
    storage: { storageSizeGB: 32, autoGrow: 'Disabled' } // lo que entra en la oferta gratuita
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
    authConfig: { activeDirectoryAuth: 'Disabled', passwordAuth: 'Enabled' }
  }
}

// Solo servicios de Azure (el rango 0.0.0.0 es la regla especial de Azure, no Internet). TLS obligatorio.
resource pgAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: pg
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource pgDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: pg
  name: 'cazachollos'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-env-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var dbEnv = [
  { name: 'POSTGRES_HOST', value: pg.properties.fullyQualifiedDomainName }
  { name: 'POSTGRES_PORT', value: '5432' }
  { name: 'POSTGRES_DB', value: pgDb.name }
  { name: 'POSTGRES_USER', value: pgUser }
  { name: 'POSTGRES_PASSWORD', secretRef: 'pg-password' }
  { name: 'POSTGRES_SSLMODE', value: 'require' }
  { name: 'LOG_LEVEL', value: 'INFO' }
]
var registries = [
  { server: roles.outputs.acrLoginServer, identity: identity.id }
]

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: '${prefix}-ingesta'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: env.id
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: { cronExpression: cron, parallelism: 1, replicaCompletionCount: 1 }
      replicaTimeout: 600
      replicaRetryLimit: 0
      registries: registries
      secrets: [{ name: 'pg-password', value: pgPassword }]
    }
    template: {
      containers: [
        {
          name: 'ingesta'
          image: image
          command: ['sh', '-c', 'alembic upgrade head && python cmd/run_ingestor.py']
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: concat(dbEnv, [
            { name: 'INGESTION_MODE', value: 'WEB' }
            { name: 'TELEGRAM_PUBLIC_CHANNELS', value: channels }
            { name: 'ACTIVE_HOURS', value: activeHours }
            { name: 'LLM_PROVIDER', value: 'azure' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: roles.outputs.openAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiDeployment }
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'LLM_MAX_CALLS_PER_DAY', value: string(llmMaxCallsPerDay) }
          ])
        }
      ]
    }
  }
}

resource dashboard 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-panel'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    environmentId: env.id
    configuration: {
      // Sin login configurado, el panel no se publica en Internet
      ingress: { external: withAuth, targetPort: 8501, transport: 'auto', allowInsecure: false }
      registries: registries
      secrets: concat(
        [{ name: 'pg-password', value: pgPassword }],
        withAuth ? [{ name: 'google-secret', value: googleClientSecret }] : []
      )
    }
    template: {
      containers: [
        {
          name: 'panel'
          image: image
          command: ['streamlit', 'run', 'app.py', '--server.port', '8501', '--server.address', '0.0.0.0']
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: concat(dbEnv, [{ name: 'ALLOWED_EMAILS', value: allowedEmails }])
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (withAuth) {
  parent: dashboard
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: { unauthenticatedClientAction: 'RedirectToLoginPage', redirectToProvider: 'google' }
    identityProviders: {
      google: {
        enabled: true
        registration: { clientId: googleClientId, clientSecretSettingName: 'google-secret' }
        login: { scopes: ['openid', 'email', 'profile'] }
      }
    }
  }
}

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: '${prefix}-budget'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      real50: { enabled: true, operator: 'GreaterThan', threshold: 50, thresholdType: 'Actual', contactEmails: budgetEmails }
      real90: { enabled: true, operator: 'GreaterThan', threshold: 90, thresholdType: 'Actual', contactEmails: budgetEmails }
      previsto100: { enabled: true, operator: 'GreaterThan', threshold: 100, thresholdType: 'Forecasted', contactEmails: budgetEmails }
    }
  }
}

output dashboardUrl string = withAuth ? 'https://${dashboard.properties.configuration.ingress.fqdn}' : ''
output dashboardFqdnWhenPublic string = '${dashboard.name}.${env.properties.defaultDomain}'
output jobName string = job.name
output postgresHost string = pg.properties.fullyQualifiedDomainName
