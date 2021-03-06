#!/usr/bin
# -*- coding: utf-8 -*- 

"""
Purpose of this script is to pull fields from SFDC and map/update to fields in Zendesk

USAGE: python S2Z-02-org-sync.py

Ideally, this should be put in a cron job and run at least hourly

"""

import sys, os
import logging.config
import json
import string
import time
import yaml
from env import MySqlTask
from env import SalesforceTask
from env import ZendeskTask

def usage(message = '', exit = True):
	"""
	Display usage information, with an error message if provided.
	"""
	if len(message) > 0:
		sys.stderr.write('\n%s\n' % message)
		sys.stderr.write('\n');
		sys.stderr.write('Usage: python S2Z-02-org-sync.py <config_file> \\\n')
		sys.stderr.write('\n')
		sys.stderr.write('Example\n')
		sys.stderr.write('       python S2Z-02-org-sync.py main_config.yml \\\n')
		sys.stderr.write('\n')
		sys.stderr.write('\n')
	if exit:
		sys.exit(1)

def setup_logging(
    default_path='logging.yml', 
    default_level=logging.INFO
):
    """Setup logging configuration

    """
    path = default_path
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = yaml.load(f.read())
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

def ProcessSfdcAccounts(results):

	processedResults = []

	for record in results:
		# SAMPLE RECORD
		#	{
		#		'Name': 'Unified Social', 
		#		'Named_Support_Engineer__c': '', 
		#		'Technical_Account_Manager__r': 
		#			{
		#				'type': 'User', 
		#				'Id': '', 
		#				'Name': 'Steve Lee'
		#			}, 
		#		'Subscription_Plan__c': 'Bronze', 
		#		'Zendesk__Domain_Mapping__c' : '',
		#		'Support_Package__c': 'Standard', 
		#		'type': 'Account', 
		#		'Id': '0013000001AAZTKAA5', 
		#		'Account_Owner_Name__c': 'John Novak',
		#		'Account_Status__c' : 'Engaged',
		#		'Username_s__c' : 'simstu'
		#	}
		try:
			tam = "tam:" + record['Technical_Account_Manager__r']['Name'].replace(" ", "_").strip()
		except:
			tam = ''

		ao 				= "ao:" + record['Account_Owner_Name__c'].replace(" ", "_").strip() if record['Account_Owner_Name__c'] != '' else ''
		nse 			= "nse:" + record['Named_Support_Engineer__c'].replace(" ", "_").strip() if record['Named_Support_Engineer__c'] != '' else ''
		domains 		= string.split(record['Zendesk__Domain_Mapping__c']) if record['Zendesk__Domain_Mapping__c'] != '' else []
		twitter 		= "twitter_rate_approval:" + record['Twitter_Rate_Approval__c'].replace(" ", "_").strip() if record['Twitter_Rate_Approval__c'] != '' else ''
		account_status 	= "account_status:" + record['Account_Status__c'].replace(" ", "_").strip() if record['Account_Status__c'] != '' else ""
		known_usernames = record['Username_s__c']
		mrr 			= "mrr:" + str(int(record['Contracted_MRR__c'])) if record['Contracted_MRR__c'] > 0 else ''
		smb_enterprise	= "type:" + record['SMB_Enterprise__c'] if record['SMB_Enterprise__c'] != '' else ''


		processedResults.append(
			{
				'Name'					: record['Name'],
				'NSE' 					: nse,
				'TAM' 					: tam,
				'Subscription' 			: record['Subscription_Plan__c'].replace(" ", ""),
				'SupportPackage' 		: record['Support_Package__c'],
				'AccountId' 			: record['Id'],
				'DomainMapping' 		: domains,
				'AccountOwner' 			: ao,
				'TwitterRateApproval' 	: twitter,
				'AccountStatus'			: account_status,
				'KnownUsernames'		: known_usernames,
				'MRR'					: mrr,
				'SMBEnterprise'			: smb_enterprise
			}
		)
	return processedResults

def UpsertZendeskOrgs(zendesk_conn, zendeskOrgs, sfdcAccounts):
	#{
	#    "organization": {
	#        "url": "https://datasiftsupport.zendesk.com/api/v2/organizations/20386337.json",
	#        "id": 20386337,
	#        "name": "DataSift",
	#        "shared_tickets": true,
	#        "shared_comments": true,
	#        "external_id": "00130000014JoNqAAK",
	#        "created_at": "2011-10-11T10:05:42Z",
	#        "updated_at": "2013-11-25T21:29:57Z",
	#        "domain_names": [
	#            "datasift.com",
	#            "mediasift.com"
	#        ],
	#        "details": "",
	#        "notes": "testing",
	#        "group_id": 20550152,
	#        "tags": [
	#            "twitter_rate_approval:not_requested",
	#            "ao:pier_barattolo"
	#        ],
	#        "organization_fields": {
	#            "account_owner": null,
	#            "known_usernames": "victor",
	#            "named_support_engineer": null,
	#            "subscription_plan": null,
	#            "twitter_rate_approval": null
	#        }
	#    }
	#}

	# Support Packages
	elite = config['zenElite']
	eliteVip = config['zenVip']
	premier = config['zenPremier']
	standard = config['zenStandard']

	zendeskName = {} # Name-based key
	zendeskExtId = {} # SFDC-based key
	zendeskString = {} # Zendesk-ID based key to store string
	apiCalls = 0
	errorCount = 0
	possibleDuplicates = []

	for org in zendeskOrgs:
		if org['external_id'] is not None:
			zendeskExtId[org['external_id']] = org['id']
			# Handle "None" types
			known_usernames = org['organization_fields']['known_usernames'] if org['organization_fields']['known_usernames'] is not None else ''

			zendeskString[org['id']] = "{0}_{1}_{2}_{3}_{4}_{5}".format(org['name'].encode('utf-8'), 
																		org['external_id'], 
																		org['group_id'], 
																		"_".join(sorted(org['domain_names'])),
																		"_".join(sorted(org['tags'])), 
																		known_usernames)
			zendeskName[org['name']] = org['id']

	for account in sfdcAccounts:
		# Assign the correct Support package
		supportPackage = account['SupportPackage']

		packages = {
			'Elite' 	: elite,
			'Elite VIP'	: eliteVip,
			'Premier'	: premier,
			'Standard'	: standard
		}

		# Assign the group ID based on the packages dictionary, else set it to standard
		group = packages.get(supportPackage, standard)

		# Set up all the tags
		tags = [ 	
					account['AccountOwner'].lower(), 
					account['TAM'].lower(),
					account['NSE'].lower(),
					account['Subscription'].lower(),
					account['TwitterRateApproval'].lower(),
					account['AccountStatus'].lower(),
					account['MRR'].lower(),
					account['SMBEnterprise'].lower()
				]
		tags = [x for x in tags if x] # remove empty strings

		organization_fields = {
				'known_usernames' : account['KnownUsernames']
			}

		# Works around issue with pipe character in name
		account_name = account['Name'].replace("|","")
		
		sfdc = "{0}_{1}_{2}_{3}_{4}_{5}".format(account_name, 
												account['AccountId'], 
												group, 
												"_".join(sorted(account['DomainMapping'])), 
												"_".join(sorted(tags)), 
												account['KnownUsernames'])
		
		# Finalize the data payload
		data = {
			"organization": {
					'name' : account_name,
					'shared_comments' : True,
					'shared_tickets' : True,
					'domain_names' : account['DomainMapping'],
					'external_id' : account['AccountId'],
					'group_id' : group,
					'tags' : tags,
					'organization_fields' : organization_fields
				}
		}	

		### FIRST, Try ID-based matching ###
		if account['AccountId'] in zendeskExtId:	
			try:
				#print "Before: " + str(data) # Before
				if sfdc != zendeskString[zendeskExtId[account['AccountId']]]:
					print "SFDC: " + sfdc
					print "ZenD: " + zendeskString[zendeskExtId[account['AccountId']]]
					orgId = zendeskExtId[account['AccountId']]
					result = zendesk_conn.update_organization(orgId, data)
					apiCalls+=1
					print "After: " + str(result) # After
					logging.debug("Zendesk Update: " + str(result))
			except Exception, err:
				print "Zendesk Update Organization Error for ID {0} : {1}".format(zendeskExtId[account['AccountId']], err)
				print err
				print data['organization']['name']
				logging.exception("Zendesk Update Organization Error for ID {0} : {1}".format(zendeskExtId[account['AccountId']], err))
				logging.warning("Data: {0}".format(data))
				errorCount+=1

		### SECOND - Try to match by organization name ###
		elif account['Name'] in zendeskName:
			try:
				print "Before: " + str(data) # Before
				orgId = zendeskName[account['Name']]
				result = zendesk_conn.update_organization(orgId, data)
				apiCalls+=1
				print "After: " + str(result) # After
			except Exception, err:
				logging.exception("Zendesk Update Organization Error for Name {0} : {1}".format(zendeskName[account['Name']], err))
				logging.warning("Data: {0}".format(data))
				errorCount+=1
		### THIRD - Try to create the organization in Zendesk ###
		else:
			try:
				logging.info("Trying to create organization: {0}".format(data))
				result = zendesk_conn.create_organization(data)
				logging.debug("Create output: {0}".format(result))
				apiCalls+=1
			except Exception, err:
				logging.exception("Zendesk Create Organization Error: {0} : {1}".format(account['Name'], err))
				logging.warning("Data: {0}".format(data))
				print err.msg
				msg = json.loads(err.msg)
				print msg
				
				if "description" in msg["details"]["name"][0]:
					if msg["details"]["name"][0]["description"] == "Name has already been taken":
						possibleDuplicates.append(account['Name'])
				else:
					print "does not exist"

				errorCount += 1

	if len(possibleDuplicates):
		print possibleDuplicates
		
	logging.info("Total Zendesk Update calls used: {0}".format(apiCalls))

	return errorCount


if __name__ == "__main__":
	if len(sys.argv) < 2:
		sys.stderr.write('Please specify the correct number of command line arguments! Need a config file\n')
		usage()

	# Set up logging
	setup_logging()

	# Load config files
	try:
		filename = sys.argv[1]
		logging.info("Trying to open configuration file {0}.".format(filename))
		f = open(filename)
		config = yaml.safe_load(f)

		logging.info("Sucessfully opened configuration file.")

		f.close()
	except Exception, err:
		logging.exception(err)
		sys.exit(1)

	# Create object for internal database methods (mySQL)
	mysqlDb = MySqlTask(config['mysql_username'], config['mysql_password'], config['mysql_host'], config['mysql_database'])

	# Create object for Salesforce methods
	sfdc = SalesforceTask(config['sfUser'], config['sfPass'], config['sfApiToken'])

	# Create object for Zendesk methods
	zd = ZendeskTask(config['zenURL'], config['zenAgent'], config['zenPass'], config['zenToken'])

	### Pull SFDC Account Info to Zendesk Organizations ###
	try:
		sfdcLastModified = sfdc.sfdc_timestamp()
		logging.info("Current Salesforce Timestamp: {0}".format(sfdcLastModified))
	except Exception, err:
		logging.exception(err)
		sys.exit()

	# Get the last modified timestamp from internal database
	startTime = mysqlDb.pull_job_timestamp('SFDC_ACCOUNTS_LAST_MODIFIED')
	logging.info("Pulling SFDC_ACCOUNTS_LAST_MODIFIED; start time of {0}".format(startTime))

	##### Extract all SFDC Accounts #####
	logging.info("Pulling Accounts from Salesforce")
	sfdcQuery = """SELECT Id, Name, Subscription_Plan__c, Support_Package__c, Zendesk__Domain_Mapping__c, 
						  Account_Owner_Name__c, Named_Support_Engineer__c, Technical_Account_Manager__r.Name, 
						  Twitter_Rate_Approval__c, Username_s__c, Account_Status__c, SMB_Enterprise__c,
						  Contracted_MRR__c  
				   FROM Account 
				   WHERE LastModifiedDate > {0}""".format(startTime)
	sfdcResults = sfdc.sfdc_query(sfdcQuery)
	sfdcAccounts = ProcessSfdcAccounts(sfdcResults['results'])


	# If there are no SFDC Account modified since the last run, update the internal 
	# timestamp and exit.
	if len(sfdcAccounts) == 0:
		mysqlDb.update_job_timestamp('SFDC_ACCOUNTS_LAST_MODIFIED', sfdcLastModified)
		logging.info("Updating SFDC_ACCOUNTS_LAST_MODIFIED timestamp.")
		logging.info("No modified SFDC Accounts. Exiting.")
		sys.exit()

	else:
		logging.info("SFDC Account(s) Pulled: {0}".format(len(sfdcAccounts)))


	##### Extract all Zendesk Organizations #####
	try:
		zendeskOrgs = zd.get_all_organizations()

	except Exception, err:
		logging.exception(err)

	##### Update Zendesk Orgs #####
	# errCount will determine if errors were encountered
	errCount = UpsertZendeskOrgs(zd, zendeskOrgs, sfdcAccounts)

	##### Update Zendesk Organization Custom Fields #####
	org_fields = zd.list_organization_fields()

	if errCount:
		logging.info("Completed syncing Zendesk Organizations and SFDC Accounts. Errors were encountered and timestamp not updated.")
	else:
		mysqlDb.update_job_timestamp('SFDC_ACCOUNTS_LAST_MODIFIED', sfdcLastModified)
		logging.info("Completed syncing Zendesk Organizations and SFDC Accounts.")

