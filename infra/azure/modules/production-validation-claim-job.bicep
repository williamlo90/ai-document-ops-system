param location string
param name string
param enabled bool = false
param environmentId string
param imageReference string
param registryServer string
param identityId string
param databaseUrlSecretUri string
param validationRunId string
param leaseSeconds int = 60
param tags object

resource job 'Microsoft.App/jobs@2025-01-01' = if (enabled) {
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
    environmentId: environmentId
    configuration: {
      triggerType: 'Manual'
      replicaRetryLimit: 0
      replicaTimeout: 300
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: databaseUrlSecretUri
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'claim-and-exit'
          image: imageReference
          command: [
            'python'
            '-m'
            'app.production_validation_claim'
          ]
          env: [
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
              name: 'PARSER_PROVIDER'
              value: 'mock'
            }
            {
              name: 'EXTRACTOR_PROVIDER'
              value: 'mock'
            }
            {
              name: 'WORKER_JOB_LEASE_SECONDS'
              value: string(leaseSeconds)
            }
            {
              name: 'PRODUCTION_VALIDATION_RUN_ID'
              value: validationRunId
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
    }
  }
}

output name string = enabled ? job!.name : ''
