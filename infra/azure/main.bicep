targetScope = 'subscription'

@description('Short environment name used in resource names and tags.')
@minLength(3)
@maxLength(12)
param environmentName string = 'validation'

@description('Azure region. Confirm service and SKU availability during preflight.')
param location string = 'southeastasia'

@description('Dedicated, disposable resource group for the Azure validation run.')
param resourceGroupName string = 'rg-ai-document-validation-sea'

@description('Exact Git commit represented by the release.')
@minLength(7)
param sourceRevision string

@description('ISO-8601 time after which the validation resources should no longer exist.')
param expiresAt string = dateTimeAdd(utcNow(), 'P1D')

@description('PostgreSQL administrator login. This is not used by application users.')
param postgresAdministratorLogin string = 'docinteladmin'

@secure()
@description('Generated for an ephemeral environment when omitted. Never place an explicit value in a committed parameter file.')
param postgresAdministratorPassword string = '${newGuid()}-Aa1!'

@secure()
param adminToken string = '${newGuid()}-${newGuid()}'

@secure()
param uploaderToken string = '${newGuid()}-${newGuid()}'

@secure()
param reviewerToken string = '${newGuid()}-${newGuid()}'

@secure()
param metricsToken string = '${newGuid()}-${newGuid()}'

var resourceToken = toLower(uniqueString(subscription().id, resourceGroupName, environmentName))
var namePrefix = 'docintel-${environmentName}-${take(resourceToken, 6)}'
var registryName = 'cr${take(resourceToken, 20)}'
var storageAccountName = 'st${take(resourceToken, 20)}'
var keyVaultName = 'kv-${take(resourceToken, 20)}'
var serviceBusNamespaceName = 'sb-${take(resourceToken, 20)}'
var postgresServerName = 'pg-${take(resourceToken, 20)}'
var documentContainerName = 'documents'
var externalDropContainerName = 'external-drop'
var functionPackageContainerName = 'function-releases'
var serviceBusQueueName = 'document-processing'
var commonTags = {
  project: 'ai-document-ops'
  environment: environmentName
  owner: 'portfolio-validation'
  sourceRevision: sourceRevision
  expiresAt: expiresAt
  managedBy: 'bicep'
}

resource validationResourceGroup 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: resourceGroupName
  location: location
  tags: commonTags
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: validationResourceGroup
  params: {
    location: location
    namePrefix: namePrefix
    tags: commonTags
  }
}

module identities 'modules/identities.bicep' = {
  name: 'identities'
  scope: validationResourceGroup
  params: {
    location: location
    namePrefix: namePrefix
    tags: commonTags
  }
}

module registry 'modules/registry.bicep' = {
  name: 'registry'
  scope: validationResourceGroup
  params: {
    location: location
    name: registryName
    tags: commonTags
    logAnalyticsWorkspaceId: monitoring.outputs.workspaceId
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  scope: validationResourceGroup
  params: {
    location: location
    name: storageAccountName
    tags: commonTags
    logAnalyticsWorkspaceId: monitoring.outputs.workspaceId
    documentContainerName: documentContainerName
    externalDropContainerName: externalDropContainerName
    functionPackageContainerName: functionPackageContainerName
  }
}

module serviceBus 'modules/service-bus.bicep' = {
  name: 'service-bus'
  scope: validationResourceGroup
  params: {
    location: location
    namespaceName: serviceBusNamespaceName
    queueName: serviceBusQueueName
    tags: commonTags
    logAnalyticsWorkspaceId: monitoring.outputs.workspaceId
  }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  scope: validationResourceGroup
  params: {
    location: location
    name: postgresServerName
    administratorLogin: postgresAdministratorLogin
    administratorPassword: postgresAdministratorPassword
    databaseName: 'docintel'
    tags: commonTags
    logAnalyticsWorkspaceId: monitoring.outputs.workspaceId
  }
}

module keyVault 'modules/key-vault.bicep' = {
  name: 'key-vault'
  scope: validationResourceGroup
  params: {
    location: location
    name: keyVaultName
    tenantId: tenant().tenantId
    tags: commonTags
    logAnalyticsWorkspaceId: monitoring.outputs.workspaceId
    databaseUrl: 'postgresql://${postgresAdministratorLogin}:${postgresAdministratorPassword}@${postgres.outputs.fqdn}:5432/docintel?sslmode=require'
    adminToken: adminToken
    uploaderToken: uploaderToken
    reviewerToken: reviewerToken
    metricsToken: metricsToken
  }
}

module containerAppsEnvironment 'modules/container-apps-environment.bicep' = {
  name: 'container-apps-environment'
  scope: validationResourceGroup
  params: {
    location: location
    name: '${namePrefix}-env'
    tags: commonTags
    logAnalyticsWorkspaceId: monitoring.outputs.workspaceId
  }
}

module roleAssignments 'modules/role-assignments.bicep' = {
  name: 'least-privilege-rbac'
  scope: validationResourceGroup
  params: {
    registryName: registry.outputs.name
    storageAccountName: storage.outputs.name
    documentContainerName: documentContainerName
    serviceBusNamespaceName: serviceBus.outputs.namespaceName
    serviceBusQueueName: serviceBus.outputs.queueName
    keyVaultName: keyVault.outputs.name
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    apiPrincipalId: identities.outputs.api.principalId
    workerPrincipalId: identities.outputs.worker.principalId
    migrationPrincipalId: identities.outputs.migration.principalId
    ingestionPrincipalId: identities.outputs.ingestion.principalId
  }
}

module ingestionFunction 'modules/ingestion-function.bicep' = {
  name: 'ingestion-function'
  scope: validationResourceGroup
  dependsOn: [
    roleAssignments
  ]
  params: {
    location: location
    name: '${namePrefix}-ingest'
    planName: '${namePrefix}-function-plan'
    storageAccountName: storage.outputs.name
    storageAccountUrl: storage.outputs.blobEndpoint
    functionPackageContainerUrl: storage.outputs.functionPackageContainerUrl
    identityId: identities.outputs.ingestion.id
    identityClientId: identities.outputs.ingestion.clientId
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    keyVaultUri: keyVault.outputs.uri
    externalDropContainerName: externalDropContainerName
    tags: commonTags
  }
}

output resourceGroupName string = validationResourceGroup.name
output location string = location
output sourceRevision string = sourceRevision
output expiresAt string = expiresAt
output namePrefix string = namePrefix
output registryName string = registry.outputs.name
output registryLoginServer string = registry.outputs.loginServer
output storageAccountName string = storage.outputs.name
output storageAccountUrl string = storage.outputs.blobEndpoint
output documentContainerName string = documentContainerName
output externalDropContainerName string = externalDropContainerName
output serviceBusNamespaceName string = serviceBus.outputs.namespaceName
output serviceBusFullyQualifiedNamespace string = serviceBus.outputs.fullyQualifiedNamespace
output serviceBusQueueName string = serviceBus.outputs.queueName
output keyVaultName string = keyVault.outputs.name
output containerAppsEnvironmentName string = containerAppsEnvironment.outputs.name
output functionAppName string = ingestionFunction.outputs.name
output apiIdentityName string = last(split(identities.outputs.api.id, '/'))
output workerIdentityName string = last(split(identities.outputs.worker.id, '/'))
output migrationIdentityName string = last(split(identities.outputs.migration.id, '/'))
