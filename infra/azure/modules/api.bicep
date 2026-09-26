param location string
param name string
param environmentId string
param imageReference string
param clamavImageReference string
param registryServer string
param identityId string
param identityClientId string
param storageAccountUrl string
param storageContainerName string
param serviceBusNamespace string
param serviceBusQueueName string
param databaseUrlSecretUri string
param adminTokenSecretUri string
param uploaderTokenSecretUri string
param reviewerTokenSecretUri string
param metricsTokenSecretUri string
param mistralApiKeySecretUri string
param extractorApiKeySecretUri string
param useRealProviders bool = false
param tags object

var baseSecrets = [
  {
    name: 'database-url'
    keyVaultUrl: databaseUrlSecretUri
    identity: identityId
  }
  {
    name: 'admin-token'
    keyVaultUrl: adminTokenSecretUri
    identity: identityId
  }
  {
    name: 'uploader-token'
    keyVaultUrl: uploaderTokenSecretUri
    identity: identityId
  }
  {
    name: 'reviewer-token'
    keyVaultUrl: reviewerTokenSecretUri
    identity: identityId
  }
  {
    name: 'metrics-token'
    keyVaultUrl: metricsTokenSecretUri
    identity: identityId
  }
]

var providerSecrets = useRealProviders ? [
  {
    name: 'mistral-api-key'
    keyVaultUrl: mistralApiKeySecretUri
    identity: identityId
  }
  {
    name: 'extractor-api-key'
    keyVaultUrl: extractorApiKeySecretUri
    identity: identityId
  }
] : []

var providerEnvironment = useRealProviders ? [
  {
    name: 'PARSER_PROVIDER'
    value: 'mistral_ocr'
  }
  {
    name: 'MISTRAL_API_KEY'
    secretRef: 'mistral-api-key'
  }
  {
    name: 'MISTRAL_ALLOWED_HOSTS'
    value: 'api.mistral.ai'
  }
  {
    name: 'EXTRACTOR_PROVIDER'
    value: 'llm_json'
  }
  {
    name: 'EXTRACTOR_API_KEY'
    secretRef: 'extractor-api-key'
  }
  {
    name: 'EXTRACTOR_ALLOWED_HOSTS'
    value: 'api.openai.com'
  }
] : [
  {
    name: 'PARSER_PROVIDER'
    value: 'mock'
  }
  {
    name: 'EXTRACTOR_PROVIDER'
    value: 'mock'
  }
]

resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      maxInactiveRevisions: 3
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
      secrets: concat(baseSecrets, providerSecrets)
    }
    template: {
      containers: [
        {
          name: 'api'
          image: imageReference
          env: concat([
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'APP_WORKSPACE_ID'
              value: 'azure-validation'
            }
            {
              name: 'STORAGE_BACKEND'
              value: 'postgres'
            }
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'DOCUMENT_STORAGE_BACKEND'
              value: 'azure-blob'
            }
            {
              name: 'AZURE_STORAGE_ACCOUNT_URL'
              value: storageAccountUrl
            }
            {
              name: 'AZURE_STORAGE_CONTAINER'
              value: storageContainerName
            }
            {
              name: 'AZURE_MANAGED_IDENTITY_CLIENT_ID'
              value: identityClientId
            }
            {
              name: 'PROCESSING_QUEUE_BACKEND'
              value: 'azure-service-bus'
            }
            {
              name: 'AZURE_SERVICE_BUS_NAMESPACE'
              value: serviceBusNamespace
            }
            {
              name: 'AZURE_SERVICE_BUS_QUEUE_NAME'
              value: serviceBusQueueName
            }
            {
              name: 'APP_ADMIN_TOKEN'
              secretRef: 'admin-token'
            }
            {
              name: 'APP_UPLOADER_TOKEN'
              secretRef: 'uploader-token'
            }
            {
              name: 'APP_REVIEWER_TOKEN'
              secretRef: 'reviewer-token'
            }
            {
              name: 'APP_METRICS_TOKEN'
              secretRef: 'metrics-token'
            }
            {
              name: 'MALWARE_SCANNING_ENABLED'
              value: 'true'
            }
            {
              name: 'MALWARE_SCANNER_BACKEND'
              value: 'clamav'
            }
            {
              name: 'CLAMAV_HOST'
              value: '127.0.0.1'
            }
            {
              name: 'CLAMAV_PORT'
              value: '3310'
            }
          ], providerEnvironment)
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 10
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/ready'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 3
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
        {
          name: 'clamav'
          image: clamavImageReference
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
        rules: [
          {
            name: 'http-concurrency'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = app.id
output name string = app.name
output fqdn string = app.properties.configuration.ingress.fqdn
