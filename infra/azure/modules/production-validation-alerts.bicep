param location string
param namePrefix string
param enabled bool = false
@secure()
param notificationEmail string = ''
param logAnalyticsWorkspaceId string
param serviceBusNamespaceName string
param serviceBusQueueName string
param tags object

resource serviceBus 'Microsoft.ServiceBus/namespaces@2024-01-01' existing = {
  name: serviceBusNamespaceName
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (enabled) {
  name: '${take(namePrefix, 44)}-validation-ag'
  location: 'global'
  tags: tags
  properties: {
    enabled: true
    groupShortName: 'docintval'
    emailReceivers: [
      {
        name: 'validation-operator'
        emailAddress: notificationEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource deadLetterAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (enabled) {
  name: '${take(namePrefix, 48)}-dlq'
  location: 'global'
  tags: tags
  properties: {
    description: 'Production validation queue has one or more dead-letter messages.'
    severity: 2
    enabled: true
    scopes: [
      serviceBus.id
    ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'DeadLetteredMessagesAboveZero'
          criterionType: 'StaticThresholdCriterion'
          metricNamespace: 'Microsoft.ServiceBus/namespaces'
          metricName: 'DeadletteredMessages'
          operator: 'GreaterThan'
          threshold: 0
          timeAggregation: 'Maximum'
          dimensions: [
            {
              name: 'EntityName'
              operator: 'Include'
              values: [
                serviceBusQueueName
              ]
            }
          ]
          skipMetricValidation: false
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
    autoMitigate: true
  }
}

resource workerFailureAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = if (enabled) {
  name: '${take(namePrefix, 44)}-worker-failure'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    displayName: 'AI Document validation worker failure'
    description: 'Worker abandoned or dead-lettered a processing message.'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    scopes: [
      logAnalyticsWorkspaceId
    ]
    criteria: {
      allOf: [
        {
          query: 'ContainerAppConsoleLogs_CL | where Log_s has_any ("queue_message_abandoned", "queue_message_dead_lettered")'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
    autoMitigate: true
    checkWorkspaceAlertsStorageConfigured: false
    skipQueryValidation: false
  }
}

resource apiFailureAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = if (enabled) {
  name: '${take(namePrefix, 48)}-api-failure'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    displayName: 'AI Document validation API 5xx or readiness failure'
    description: 'API emitted a 5xx response or failed readiness check.'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    scopes: [
      logAnalyticsWorkspaceId
    ]
    criteria: {
      allOf: [
        {
          query: '''
ContainerAppConsoleLogs_CL
| where (Log_s has "request_completed" and Log_s contains '"status_code": 5') or Log_s has "not_ready"
'''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [
        actionGroup.id
      ]
    }
    autoMitigate: true
    checkWorkspaceAlertsStorageConfigured: false
    skipQueryValidation: false
  }
}

output actionGroupId string = enabled ? actionGroup.id : ''
