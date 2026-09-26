@description('Outputs from the foundation deployment identify the existing resources.')
param namePrefix string
param location string
param sourceRevision string
param expiresAt string
param registryName string
param storageAccountName string
param documentContainerName string = 'documents'
param serviceBusNamespaceName string
param serviceBusQueueName string = 'document-processing'
param keyVaultName string
param containerAppsEnvironmentName string
param apiIdentityName string
param workerIdentityName string
param migrationIdentityName string

@description('Application image in registry/repository@sha256:digest form.')
param imageReference string

@description('ClamAV image in registry/repository@sha256:digest form.')
param clamavImageReference string

@description('Enable only after provider keys exist in Key Vault.')
param useRealProviders bool = false

var commonTags = {
  project: 'ai-document-ops'
  environment: 'validation'
  owner: 'portfolio-validation'
  sourceRevision: sourceRevision
  expiresAt: expiresAt
  managedBy: 'bicep'
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource serviceBus 'Microsoft.ServiceBus/namespaces@2024-01-01' existing = {
  name: serviceBusNamespaceName
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' existing = {
  name: containerAppsEnvironmentName
}

resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: apiIdentityName
}

resource workerIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: workerIdentityName
}

resource migrationIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: migrationIdentityName
}

var databaseUrlSecretUri = '${vault.properties.vaultUri}secrets/database-url'
var mistralApiKeySecretUri = '${vault.properties.vaultUri}secrets/mistral-api-key'
var extractorApiKeySecretUri = '${vault.properties.vaultUri}secrets/extractor-api-key'

module api 'modules/api.bicep' = {
  name: 'api-runtime'
  params: {
    location: location
    name: '${namePrefix}-api'
    environmentId: environment.id
    imageReference: imageReference
    clamavImageReference: clamavImageReference
    registryServer: registry.properties.loginServer
    identityId: apiIdentity.id
    identityClientId: apiIdentity.properties.clientId
    storageAccountUrl: storage.properties.primaryEndpoints.blob
    storageContainerName: documentContainerName
    serviceBusNamespace: '${serviceBus.name}.servicebus.windows.net'
    serviceBusQueueName: serviceBusQueueName
    databaseUrlSecretUri: databaseUrlSecretUri
    adminTokenSecretUri: '${vault.properties.vaultUri}secrets/admin-token'
    uploaderTokenSecretUri: '${vault.properties.vaultUri}secrets/uploader-token'
    reviewerTokenSecretUri: '${vault.properties.vaultUri}secrets/reviewer-token'
    metricsTokenSecretUri: '${vault.properties.vaultUri}secrets/metrics-token'
    mistralApiKeySecretUri: mistralApiKeySecretUri
    extractorApiKeySecretUri: extractorApiKeySecretUri
    useRealProviders: useRealProviders
    tags: commonTags
  }
}

module worker 'modules/worker.bicep' = {
  name: 'worker-runtime'
  params: {
    location: location
    name: '${namePrefix}-worker'
    environmentId: environment.id
    imageReference: imageReference
    registryServer: registry.properties.loginServer
    identityId: workerIdentity.id
    identityClientId: workerIdentity.properties.clientId
    storageAccountUrl: storage.properties.primaryEndpoints.blob
    storageContainerName: documentContainerName
    serviceBusNamespace: '${serviceBus.name}.servicebus.windows.net'
    serviceBusNamespaceName: serviceBus.name
    serviceBusQueueName: serviceBusQueueName
    databaseUrlSecretUri: databaseUrlSecretUri
    mistralApiKeySecretUri: mistralApiKeySecretUri
    extractorApiKeySecretUri: extractorApiKeySecretUri
    useRealProviders: useRealProviders
    tags: commonTags
  }
}

module migration 'modules/migration-job.bicep' = {
  name: 'migration-runtime'
  params: {
    location: location
    name: '${namePrefix}-migrate'
    environmentId: environment.id
    imageReference: imageReference
    registryServer: registry.properties.loginServer
    identityId: migrationIdentity.id
    databaseUrlSecretUri: databaseUrlSecretUri
    tags: commonTags
  }
}

output apiName string = api.outputs.name
output apiUrl string = 'https://${api.outputs.fqdn}'
output workerName string = worker.outputs.name
output migrationJobName string = migration.outputs.name
