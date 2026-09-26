param location string
param namePrefix string
param storageAccountName string
param functionAppName string
param externalDropContainerName string = 'external-drop'
param sourceRevision string
param expiresAt string

var tags = {
  project: 'ai-document-ops'
  environment: 'validation'
  owner: 'portfolio-validation'
  sourceRevision: sourceRevision
  expiresAt: expiresAt
  managedBy: 'bicep'
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' existing = {
  name: functionAppName
}

module eventGrid 'modules/event-grid.bicep' = {
  name: 'event-grid-ingestion'
  params: {
    location: location
    namePrefix: namePrefix
    storageAccountId: storage.id
    functionAppId: functionApp.id
    externalDropContainerName: externalDropContainerName
    tags: tags
  }
}

output systemTopicId string = eventGrid.outputs.systemTopicId
output eventSubscriptionId string = eventGrid.outputs.eventSubscriptionId
