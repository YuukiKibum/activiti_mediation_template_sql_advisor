# Golden Agent Samples

Use these as regression/evaluation cases for the Mediation SQL Advisor Agent.

## golden_001_rename_existing_attribute

**User requirement:** For Prepaid Base Plan ECM request, rename existing attribute poAttributes to poAttributeList.

- **expected_change_type:** `RENAME_ATTRIBUTE`
- **expected_template_id:** `MT_ECM_PRE_BASEPLAN`
- **expected_attribute_name:** `poAttributes`
- **expected_new_attribute_name:** `poAttributeList`
- **notes:** `Tests deterministic template resolution and ATTRIBUTE_NAME update.`

```sql
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_NAME = 'poAttributeList',
    MODIFIED_USER_ID = USER,
    MODIFIED_DATE = CURRENT_TIMESTAMP
WHERE TEMPLATE_ID = 'MT_ECM_PRE_BASEPLAN'
  AND ATTRIBUTE_NAME = 'poAttributes';
```

## golden_002_append_to_existing_attribute_value

**User requirement:** For Prepaid Base Plan ECM request, add ccat_sample_value as Sample inside poAttributes.

- **expected_change_type:** `APPEND_TO_ATTRIBUTE_VALUE`
- **expected_template_id:** `MT_ECM_PRE_BASEPLAN`
- **expected_attribute_name:** `poAttributes`
- **expected_expression_fragment:** `ccat_sample_value=VAL_Sample;`
- **notes:** `Tests append behavior without rewriting the full CLOB value.`

```sql
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_VALUE = ATTRIBUTE_VALUE || 'ccat_sample_value=VAL_Sample;',
    MODIFIED_USER_ID = USER,
    MODIFIED_DATE = CURRENT_TIMESTAMP
WHERE TEMPLATE_ID = 'MT_ECM_PRE_BASEPLAN'
  AND ATTRIBUTE_NAME = 'poAttributes'
  AND INSTR(ATTRIBUTE_VALUE, 'ccat_sample_value=VAL_Sample;') = 0;
```

## golden_003_add_new_attribute_with_boolean_mapping

**User requirement:** For Prepaid Base Plan RTF request, add a new attribute AddToBillFlagCopy. If addToBill is false set false, otherwise true.

- **expected_change_type:** `ADD_NEW_ATTRIBUTE`
- **expected_template_id:** `MT_RTF_TC_PREP_PLAN`
- **expected_attribute_name:** `AddToBillFlagCopy`
- **expected_expression:** `addToBill#false|false,true|true`
- **notes:** `Tests English-to-expression compilation for # dictionary mapping.`

```sql
INSERT INTO ACT_MEDIATION_PARAMETER (
    PARAM_ID, TEMPLATE_ID, ATTRIBUTE_NAME, CREATED_USER_ID, MODIFIED_USER_ID, CREATED_DATE, MODIFIED_DATE, ATTRIBUTE_VALUE
)
SELECT
    (SELECT NVL(MAX(PARAM_ID), 0) + 1 FROM ACT_MEDIATION_PARAMETER),
    'MT_RTF_TC_PREP_PLAN',
    'AddToBillFlagCopy',
    USER,
    USER,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP,
    'addToBill#false|false,true|true'
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1
    FROM ACT_MEDIATION_PARAMETER
    WHERE TEMPLATE_ID = 'MT_RTF_TC_PREP_PLAN'
      AND ATTRIBUTE_NAME = 'AddToBillFlagCopy'
);
```

## golden_004_attribute_already_exists

**User requirement:** For Prepaid Base Plan RTF request, add AddToBillFlag. If addToBill is false set false, otherwise true.

- **expected_change_type:** `ADD_NEW_ATTRIBUTE`
- **expected_template_id:** `MT_RTF_TC_PREP_PLAN`
- **expected_attribute_name:** `AddToBillFlag`
- **expected_expression:** `addToBill#false|false,true|true`
- **expected_agent_behavior:** `Return a safe message saying the attribute already exists and show the existing ATTRIBUTE_VALUE.`
- **notes:** `Tests duplicate prevention using the TEMPLATE_ID + ATTRIBUTE_NAME unique key.`

```sql
-- No INSERT should be generated because AddToBillFlag already exists for MT_RTF_TC_PREP_PLAN in the seed data.
```

## golden_005_update_static_value

**User requirement:** For Prepaid STK Notify Store request, change POType from Add-on to Base Plan.

- **expected_change_type:** `UPDATE_ATTRIBUTE_VALUE`
- **expected_template_id:** `MT_PREPAID_STK_NOTIFY_STORE`
- **expected_attribute_name:** `POType`
- **expected_expression:** `VAL_Base Plan`
- **notes:** `Tests static value generation using VAL_.`

```sql
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_VALUE = 'VAL_Base Plan',
    MODIFIED_USER_ID = USER,
    MODIFIED_DATE = CURRENT_TIMESTAMP
WHERE TEMPLATE_ID = 'MT_PREPAID_STK_NOTIFY_STORE'
  AND ATTRIBUTE_NAME = 'POType';
```

## golden_006_rename_existing_header_attribute

**User requirement:** For Prepaid STK Update Product Store request, rename X-TIB-RequestedSystem to X-RequestedSystem.

- **expected_change_type:** `RENAME_ATTRIBUTE`
- **expected_template_id:** `MT_PREPAID_STK_UPD_PROD_STORE`
- **expected_attribute_name:** `X-TIB-RequestedSystem`
- **expected_new_attribute_name:** `X-RequestedSystem`
- **notes:** `Tests rename flow on a header-style request attribute.`

```sql
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_NAME = 'X-RequestedSystem',
    MODIFIED_USER_ID = USER,
    MODIFIED_DATE = CURRENT_TIMESTAMP
WHERE TEMPLATE_ID = 'MT_PREPAID_STK_UPD_PROD_STORE'
  AND ATTRIBUTE_NAME = 'X-TIB-RequestedSystem';
```

## golden_007_update_long_boolean_mapping

**User requirement:** For Prepaid IN Group Offer, set ThirdPartySub_Category so third party subscription enabled true maps to 1 and false maps to 0 as a long value.

- **expected_change_type:** `UPDATE_ATTRIBUTE_VALUE`
- **expected_template_id:** `PREPAID_IN_GROUP_OFFER_MT`
- **expected_attribute_name:** `ThirdPartySub_Category`
- **expected_expression:** `$LONG_allowances.otherAllowances.thirdPartySubscription.enabled#true|1,false|0`
- **notes:** `Tests $LONG_ plus # dictionary mapping expression generation.`

```sql
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_VALUE = '$LONG_allowances.otherAllowances.thirdPartySubscription.enabled#true|1,false|0',
    MODIFIED_USER_ID = USER,
    MODIFIED_DATE = CURRENT_TIMESTAMP
WHERE TEMPLATE_ID = 'PREPAID_IN_GROUP_OFFER_MT'
  AND ATTRIBUTE_NAME = 'ThirdPartySub_Category';
```

## golden_008_template_missing

**User requirement:** For Prepaid Base Plan XYZ request, add AddToBillFlagCopy with addToBill false as false and true as true.

- **expected_change_type:** `ADD_NEW_ATTRIBUTE`
- **expected_template_id:** `None`
- **expected_agent_behavior:** `Do not guess TEMPLATE_ID. Ask user to update template_registry.yaml with the correct TEMPLATE_ID for Prepaid Base Plan XYZ.`
- **notes:** `Tests missing template handling.`
