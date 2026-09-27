param location string
param name string
param environmentId string
param imageReference string
param registryServer string
param identityId string
param identityClientId string
param storageAccountUrl string
param storageContainerName string
param serviceBusNamespace string
param serviceBusNamespaceName string
param serviceBusQueueName string
param databaseUrlSecretUri string
param mistralApiKeySecretUri string
param extractorApiKeySecretUri string
param useRealProviders bool = false
param tags object

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
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
      secrets: concat([
        {
          name: 'database-url'
          keyVaultUrl: databaseUrlSecretUri
          identity: identityId
        }
      ], providerSecrets)
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: imageReference
          command: [
            'python'
            '-m'
            'app.worker_loop'
          ]
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
              name: 'UPLOAD_ROOT'
              value: '/tmp/docintel/uploads'
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
              name: 'WORKER_POLL_SECONDS'
              value: '1'
            }
            {
              name: 'WORKER_MAX_IDLE_POLL_SECONDS'
              value: '30'
            }
          ], providerEnvironment)
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        pollingInterval: 15
        cooldownPeriod: 60
        rules: [
          {
            name: 'service-bus-backlog'
            custom: {
              type: 'azure-servicebus'
              identity: identityId
              metadata: {
                queueName: serviceBusQueueName
                namespace: serviceBusNamespaceName
                messageCount: '5'
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
