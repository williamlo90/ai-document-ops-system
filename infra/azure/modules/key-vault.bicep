param location string
param name string
param tenantId string
param tags object
param logAnalyticsWorkspaceId string
@secure()
param databaseUrl string
@secure()
param adminToken string
@secure()
param uploaderToken string
@secure()
param reviewerToken string
@secure()
param metricsToken string

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enablePurgeProtection: false
    enableRbacAuthorization: true
    enableSoftDelete: true
    publicNetworkAccess: 'Enabled'
    softDeleteRetentionInDays: 7
  }
}

resource databaseUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'database-url'
  properties: {
    value: databaseUrl
  }
}

resource adminTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'admin-token'
  properties: {
    value: adminToken
  }
}

resource uploaderTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'uploader-token'
  properties: {
    value: uploaderToken
  }
}

resource reviewerTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'reviewer-token'
  properties: {
    value: reviewerToken
  }
}

resource metricsTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'metrics-token'
  properties: {
    value: metricsToken
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'send-to-log-analytics'
  scope: vault
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

output id string = vault.id
output name string = vault.name
output uri string = vault.properties.vaultUri
output databaseUrlSecretUri string = '${vault.properties.vaultUri}secrets/${databaseUrlSecret.name}'
output adminTokenSecretUri string = '${vault.properties.vaultUri}secrets/${adminTokenSecret.name}'
output uploaderTokenSecretUri string = '${vault.properties.vaultUri}secrets/${uploaderTokenSecret.name}'
output reviewerTokenSecretUri string = '${vault.properties.vaultUri}secrets/${reviewerTokenSecret.name}'
output metricsTokenSecretUri string = '${vault.properties.vaultUri}secrets/${metricsTokenSecret.name}'
output mistralApiKeySecretUri string = '${vault.properties.vaultUri}secrets/mistral-api-key'
output extractorApiKeySecretUri string = '${vault.properties.vaultUri}secrets/extractor-api-key'
