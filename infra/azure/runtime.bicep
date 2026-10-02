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
param validationSinkIdentityName string
param validationStateContainerName string = 'validation-sink-state'
param logAnalyticsWorkspaceId string

@description('Application image in registry/repository@sha256:digest form.')
param imageReference string

@description('ClamAV image in registry/repository@sha256:digest form.')
param clamavImageReference string

@description('Enable only after provider keys exist in Key Vault.')
param useRealProviders bool = false

@description('Create short-lived Azure Monitor alerts for the controlled validation run.')
param enableProductionValidationAlerts bool = false

@description('Enable the isolated ambiguous-outcome ERPNext-compatible validation sink.')
param enableProductionValidationSink bool = false

@description('Enable the manual guarded worker claim-and-exit validation job.')
param enableProductionValidationClaimJob bool = false

@description('Exact production-validation run ID. Required when the validation sink or claim job is enabled.')
param productionValidationRunId string = ''

@secure()
param productionValidationSinkSecret string = '${newGuid()}-${newGuid()}'

@secure()
@description('Local-only notification address. Required only when validation alerts are enabled.')
param validationAlertEmail string = ''

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

resource validationSinkIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: validationSinkIdentityName
}

var databaseUrlSecretUri = '${vault.properties.vaultUri}secrets/database-url'
var mistralApiKeySecretUri = '${vault.properties.vaultUri}secrets/mistral-api-key'
var extractorApiKeySecretUri = '${vault.properties.vaultUri}secrets/extractor-api-key'

module productionValidationSink 'modules/production-validation-sink.bicep' = {
  name: 'production-validation-sink'
  params: {
    location: location
    name: '${take(namePrefix, 16)}-validation-sink'
    enabled: enableProductionValidationSink
    environmentId: environment.id
    imageReference: imageReference
    registryServer: registry.properties.loginServer
    identityId: validationSinkIdentity.id
    identityClientId: validationSinkIdentity.properties.clientId
    storageAccountUrl: storage.properties.primaryEndpoints.blob
    storageContainerName: validationStateContainerName
    validationRunId: productionValidationRunId
    validationSecret: productionValidationSinkSecret
    tags: commonTags
  }
}

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
    useProductionValidationSink: enableProductionValidationSink
    productionValidationSinkBaseUrl: enableProductionValidationSink ? 'https://${productionValidationSink.outputs.fqdn}' : ''
    productionValidationSinkHost: productionValidationSink.outputs.fqdn
    productionValidationSinkSecret: productionValidationSinkSecret
    tags: commonTags
  }
}

module worker 'modules/worker.bicep' = {
  name: 'worker-runtime'
  params: {
    location: location
    name: '${take(namePrefix, 25)}-worker'
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
    name: '${take(namePrefix, 24)}-migrate'
    environmentId: environment.id
    imageReference: imageReference
    registryServer: registry.properties.loginServer
    identityId: migrationIdentity.id
    databaseUrlSecretUri: databaseUrlSecretUri
    tags: commonTags
  }
}

module productionValidationClaimJob 'modules/production-validation-claim-job.bicep' = {
  name: 'production-validation-claim-job'
  params: {
    location: location
    name: '${take(namePrefix, 19)}-claim-exit'
    enabled: enableProductionValidationClaimJob
    environmentId: environment.id
    imageReference: imageReference
    registryServer: registry.properties.loginServer
    identityId: workerIdentity.id
    databaseUrlSecretUri: databaseUrlSecretUri
    validationRunId: productionValidationRunId
    tags: commonTags
  }
}

module productionValidationAlerts 'modules/production-validation-alerts.bicep' = {
  name: 'production-validation-alerts'
  params: {
    location: location
    namePrefix: namePrefix
    enabled: enableProductionValidationAlerts
    notificationEmail: validationAlertEmail
    logAnalyticsWorkspaceId: logAnalyticsWorkspaceId
    serviceBusNamespaceName: serviceBusNamespaceName
    serviceBusQueueName: serviceBusQueueName
    tags: commonTags
  }
}

output apiName string = api.outputs.name
output apiUrl string = 'https://${api.outputs.fqdn}'
output workerName string = worker.outputs.name
output migrationJobName string = migration.outputs.name
output validationActionGroupId string = productionValidationAlerts.outputs.actionGroupId
output validationSinkName string = enableProductionValidationSink ? '${take(namePrefix, 16)}-validation-sink' : ''
output validationClaimJobName string = productionValidationClaimJob.outputs.name
