param location string
param namePrefix string
param tags object

resource api 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-api-id'
  location: location
  tags: tags
}

resource worker 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-worker-id'
  location: location
  tags: tags
}

resource migration 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-migration-id'
  location: location
  tags: tags
}

resource ingestion 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-ingestion-id'
  location: location
  tags: tags
}

output api object = {
  id: api.id
  clientId: api.properties.clientId
  principalId: api.properties.principalId
}
output worker object = {
  id: worker.id
  clientId: worker.properties.clientId
  principalId: worker.properties.principalId
}
output migration object = {
  id: migration.id
  clientId: migration.properties.clientId
  principalId: migration.properties.principalId
}
output ingestion object = {
  id: ingestion.id
  clientId: ingestion.properties.clientId
  principalId: ingestion.properties.principalId
}
