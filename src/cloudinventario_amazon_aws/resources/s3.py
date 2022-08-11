import logging
import boto3, json
from pprint import pprint
import botocore.exceptions as aws_exception
from botocore.exceptions import ClientError

from cloudinventario.helpers import CloudInvetarioResource

def setup(resource, collector):
  return CloudInventarioS3(resource, collector)

class CloudInventarioS3(CloudInvetarioResource):

  def __init__(self, resource, collector):
    super().__init__(resource, collector)

  def _login(self, session):
    self.session = session
    self.client = self.get_client()

  def _get_client(self):
    client = self.session.client('s3')
    return client

  def _fetch(self):
    data = []
    
    for bucket in self.client.list_buckets()['Buckets']:
      data.append(self._process_resource(bucket['Name']))

    return data

  def _process_resource(self, bucket_name):
    details = {}

    try: # acl
      acl = self.client.get_bucket_acl(Bucket=bucket_name)
      acl.pop("ResponseMetadata", None)
      details["acl"] = acl
      owner_id = acl['Owner']['ID']
      acl = acl['Grants']
    except ClientError as error:
      owner_id = None
      acl = None
      logging.info("The acl of the following bucket was not found: {}, you need the \"READ_ACP\" permission".format(bucket_name))
    except Exception as error:
      raise error

    try: # location
      location = self.client.get_bucket_location(Bucket=bucket_name)
      location.pop("ResponseMetadata", None)
      details["location"] = location
      location = location['LocationConstraint']
    except ClientError as error:
      location = None
      logging.info("The acl of the following bucket was not found: {}, you must be owner".format(bucket_name))
    except Exception as error:
      raise error

    try: # ownership controls
      ownership_controls = self.client.get_bucket_ownership_controls(Bucket=bucket_name)['OwnershipControls']
      ownership_controls.pop("ResponseMetadata", None)
      details["ownership_controls"] = ownership_controls
    except ClientError as error:
      ownership_controls = None
      logging.info("The ownership controls of the following bucket were not found: {}, you need the \"S3:GetBucketOwnershipControls\" permission".format(bucket_name))
    except Exception as error:
      raise error

    try: # policy status
      policy_status = self.client.get_bucket_policy_status(Bucket=bucket_name)['PolicyStatus']
      policy_status.pop("ResponseMetadata", None)
      details["policy_status"] = policy_status
    except ClientError as error:
      policy_status = None
      logging.info("The acl of the following bucket was not found: {}, you need the \"S3:GetBucketPolicyStatus\" permission".format(bucket_name))
    except Exception as error:
      raise error

    try: # website
      website = self.client.get_bucket_website(Bucket=bucket_name)
      website.pop("ResponseMetadata", None)
      details["website"] = website
    except ClientError as error:
      website = None
      logging.info("The website of the following bucket was not found: {}, you need the \"S3:GetBucketWebsite\" permission".format(bucket_name))
    except Exception as error:
      raise error

    try: # versioning
      versioning = self.client.get_bucket_versioning(Bucket=bucket_name)
      versioning.pop("ResponseMetadata", None)
      details["versioning"] = versioning
      if 'Status' in versioning:
        versioning = versioning['Status']  
      else:
        raise KeyError('Status not found in versioning')
    except KeyError as error:
      logging.info(f"KeyError: {error}")
    except ClientError as error:
      versioning = None
      logging.info("The acl of the following bucket was not found: {}, you must be owner".format(bucket_name))
    except Exception as error:
      raise error

    try: # tags
      tags = self.client.get_bucket_tagging(Bucket=bucket_name)
      tags.pop('ResponseMetadata', None)
      details["tags"] = tags
      tags = self.collector._get_tags(tags, 'TagSet')
    except ClientError as error:
      tags = None
      logging.info("The tags of the following bucket were not found: {}, you need the \"s3:GetBucketTagging\" permission".format(bucket_name))
    except Exception as error:
      raise error

    data = {
      "acl": acl,
      "location": location,
      "ownership_controls": ownership_controls,
      "policy_status": policy_status,
      "versioning": versioning,
      "website": website,
      "name": bucket_name,
      "uniqueid": bucket_name,
      "owner": owner_id,
      "tags": tags
    }

    return self.new_record(self.res_type, data, details)
