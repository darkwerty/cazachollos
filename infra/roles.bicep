// Permisos de la identidad de CazaChollos sobre recursos que ya existen en otro grupo (los de Mea culpa):
// descargar imágenes del Container Registry y llamar a Azure OpenAI. Sin claves.
targetScope = 'resourceGroup'

param principalId string
param acrName string
param openAiAccountName string

var acrPullRole = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull
var openAiUserRole = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource openAi 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: openAiAccountName
}

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, principalId, acrPullRole)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

resource llm 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAi.id, principalId, openAiUserRole)
  scope: openAi
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRole)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output openAiEndpoint string = openAi.properties.endpoint
output acrLoginServer string = acr.properties.loginServer
