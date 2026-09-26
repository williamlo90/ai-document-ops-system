param location string
param namePrefix string
param storageAccountId string
param functionAppId string
param functionName string = 'BlobCreatedIngestion'
param externalDropContainerName string = 'external-drop'
param tags object

resource systemTopic 'Microsoft.EventGrid/systemTopics@2022-06-15' = {
  name: '${namePrefix}-blob-events'
  location: location
  tags: tags
  properties: {
    source: storageAccountId
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

resource subscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2022-06-15' = {
  parent: systemTopic
  name: 'blob-created-to-ingestion'
  properties: {
    destination: {
      endpointType: 'AzureFunction'
      properties: {
        resourceId: '${functionAppId}/functions/${functionName}'
        maxEventsPerBatch: 1
        preferredBatchSizeInKilobytes: 64
      }
    }
    eventDeliverySchema: 'EventGridSchema'
    filter: {
      includedEventTypes: [
        'Microsoft.Storage.BlobCreated'
      ]
      isSubjectCaseSensitive: false
      subjectBeginsWith: '/blobServices/default/containers/${externalDropContainerName}/blobs/'
    }
    retryPolicy: {
      eventTimeToLiveInMinutes: 60
      maxDeliveryAttempts: 10
    }
  }
}

output systemTopicId string = systemTopic.id
output eventSubscriptionId string = subscription.id
