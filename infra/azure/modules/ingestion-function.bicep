param location string
param name string
param planName string
param storageAccountName string
param storageAccountUrl string
param functionPackageContainerUrl string
param identityId string
param identityClientId string
param applicationInsightsConnectionString string
param keyVaultUri string
param externalDropContainerName string
param tags object

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: name
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    clientAffinityEnabled: false
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    serverFarmId: plan.id
    siteConfig: {
      ftpsState: 'Disabled'
      http20Enabled: true
      minTlsVersion: '1.2'
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: functionPackageContainerUrl
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: identityId
          }
        }
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
      scaleAndConcurrency: {
        instanceMemoryMB: 2048
        maximumInstanceCount: 40
      }
    }
  }
}

resource appSettings 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: functionApp
  name: 'appsettings'
  properties: {
    APPLICATIONINSIGHTS_AUTHENTICATION_STRING: 'ClientId=${identityClientId};Authorization=AAD'
    APPLICATIONINSIGHTS_CONNECTION_STRING: applicationInsightsConnectionString
    AzureWebJobsStorage__accountName: storageAccountName
    AzureWebJobsStorage__clientId: identityClientId
    AzureWebJobsStorage__credential: 'managedidentity'
    FUNCTIONS_EXTENSION_VERSION: '~4'
    FUNCTIONS_WORKER_RUNTIME: 'python'
    API_BASE_URL: 'https://pending.invalid'
    KEY_VAULT_URI: keyVaultUri
    STORAGE_ACCOUNT_URL: storageAccountUrl
    EXTERNAL_DROP_CONTAINER: externalDropContainerName
    AZURE_CLIENT_ID: identityClientId
  }
}

output id string = functionApp.id
output name string = functionApp.name
output defaultHostName string = functionApp.properties.defaultHostName
