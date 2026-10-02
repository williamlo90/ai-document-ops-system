param location string
param name string
param enabled bool = false
param environmentId string
param imageReference string
param registryServer string
param identityId string
param identityClientId string
param storageAccountUrl string
param storageContainerName string
param validationRunId string
@secure()
param validationSecret string
param tags object

resource app 'Microsoft.App/containerApps@2025-01-01' = if (enabled) {
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
      maxInactiveRevisions: 1
      ingress: {
        allowInsecure: false
        external: false
        targetPort: 8080
        transport: 'http'
      }
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
      secrets: [
        {
          name: 'validation-sink-secret'
          value: validationSecret
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'validation-sink'
          image: imageReference
          command: [
            'python'
            '-m'
            'app.production_validation_sink'
          ]
          env: [
            {
              name: 'APP_ENV'
              value: 'production'
            }
            {
              name: 'VALIDATION_SINK_ENABLED'
              value: 'true'
            }
            {
              name: 'PRODUCTION_VALIDATION_RUN_ID'
              value: validationRunId
            }
            {
              name: 'VALIDATION_SINK_SECRET'
              secretRef: 'validation-sink-secret'
            }
            {
              name: 'VALIDATION_SINK_RESPONSE_DELAY_SECONDS'
              value: '5'
            }
            {
              name: 'VALIDATION_SINK_STORAGE_URL'
              value: storageAccountUrl
            }
            {
              name: 'VALIDATION_SINK_CONTAINER'
              value: storageContainerName
            }
            {
              name: 'AZURE_MANAGED_IDENTITY_CLIENT_ID'
              value: identityClientId
            }
            {
              name: 'PORT'
              value: '8080'
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output fqdn string = enabled ? app!.properties.configuration.ingress.fqdn : ''
