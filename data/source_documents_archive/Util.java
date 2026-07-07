package ae.etisalat.activiti.util;

import java.beans.IntrospectionException;
import java.beans.PropertyDescriptor;
import java.beans.XMLDecoder;
import java.beans.XMLEncoder;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.io.Serializable;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.UnsupportedEncodingException;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.sql.Timestamp;
import java.text.DateFormat;
import java.text.DecimalFormat;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.Collection;
import java.util.Collections;
import java.util.Date;
import java.util.Enumeration;
import java.util.GregorianCalendar;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.StringTokenizer;
import java.util.TimeZone;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.jms.JMSException;
import javax.jms.MapMessage;
import javax.xml.bind.JAXBContext;
import javax.xml.bind.JAXBException;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;
import javax.xml.datatype.DatatypeConfigurationException;
import javax.xml.datatype.DatatypeConstants;
import javax.xml.datatype.DatatypeFactory;
import javax.xml.datatype.XMLGregorianCalendar;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.Transformer;
import javax.xml.transform.TransformerException;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import javax.xml.xpath.XPath;
import javax.xml.xpath.XPathConstants;
import javax.xml.xpath.XPathExpressionException;
import javax.xml.xpath.XPathFactory;

import org.activiti.engine.delegate.DelegateExecution;
import org.apache.commons.lang.exception.ExceptionUtils;
import org.apache.commons.lang3.StringUtils;
import org.apache.logging.log4j.Level;
import org.json.JSONException;
import org.json.JSONObject;
import org.springframework.http.HttpMethod;
import org.w3c.dom.Node;
import org.xml.sax.InputSource;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.jayway.jsonpath.Configuration;
import com.jayway.jsonpath.JsonPath;
import com.jayway.jsonpath.Option;

import ae.etisalat.activiti.dbo.implementation.DBOSessionVariables;
import ae.etisalat.activiti.dbo.serializer.implementation.Serializer;
import ae.etisalat.activiti.jersey.JerseyClientUtil;
import ae.etisalat.activiti.jpa.entities.ActivitiMediationParameter;
import ae.etisalat.activiti.jpa.entities.ActivitiMediationTemplate;
import ae.etisalat.activiti.jpa.entities.ActivitiNetworkAudit;
import ae.etisalat.activiti.jpa.entities.ActivitiSetting;
import ae.etisalat.activiti.logger.ActivitiLogger;
import ae.etisalat.activiti.model.Config;
import ae.etisalat.bespoke.dto.baseplan.IProjectDTO;
import ae.etisalat.bespoke.entities.BespokeProject;
import ae.etisalat.bespoke.jpa.shared.IEntityProjectDTO;
import ae.etisalat.bespoke.transformers.EntityToDataModelTransformer;
import ae.etisalat.bespoke2.dto.NonEtisalatDeviceAddon;
import ae.etisalat.postpaid.dto.DiscountAddon;
import net.minidev.json.JSONArray;

public class Util {
	static final ActivitiLogger logger = ActivitiLogger.getLogger(Util.class.getName());
	static final ActivitiLogger networkLogger = ActivitiLogger.getLogger("NetworkLogger");

	private static Gson gson = new Gson();

	private static final String JSON_PATH_TOKEN = "$.";
	private static final String JSON_CONFIG_TOKEN="$C.";
	
	private static final String JSON_PATH_TOKEN_REGEXP = "\\$\\.";
	private static final String JSON_CONFIG_TOKEN_REGEXP="\\$C\\.";
	private static final Configuration conf = Configuration.defaultConfiguration()
			.addOptions(Option.DEFAULT_PATH_LEAF_TO_NULL);
	private static final String[] DATE_FORMATS = { "MMM d, yyyy HH:mm:ss a", "dd-MM-yyyy",
			"dd/MM/yyyy", "dd-MMM-yyyy" };

	private static DecimalFormat df2 = new DecimalFormat("#.##");

	Pattern asciipattern = null;
	private static Pattern complexMethodPattern = null;
	private static Pattern paramsPattern = null;
	private static Pattern paramValue = null;

	static {
		complexMethodPattern = Pattern.compile("^\\$[^_]+_");
		paramsPattern = Pattern.compile("([\\\"'])(?:(?=(\\\\?))\\2.)*?\\1");
		paramValue = Pattern.compile("[\"|']{1}(.+)[\"|']{1}");
	}

	public Util() {
		asciipattern = Pattern.compile("[\\p{ASCII}]+");
	}

	public boolean isAscii(String inputStr) {
		Matcher matcher = asciipattern.matcher(inputStr);
		if (matcher.matches())
			return true;
		else
			return false;
	}

	public static String extractAttributeMethod(String attribute) {
		Matcher matcher = complexMethodPattern.matcher(attribute);
		if (matcher.find()) {
			return matcher.group(0);
		}
		return null;
	}

	public static List<String> extractMethodParams(String method) {
		Matcher matcher = paramsPattern.matcher(method);
		List<String> params = new ArrayList<>();
		while (matcher.find()) {
			Matcher exact = paramValue.matcher(matcher.group(0));
			if (exact.find()) {
				if (exact.groupCount() > 0) {
					params.add(exact.group(1));
				}
			}
		}
		return params;
	}

	public static void sleep(int seconds) {
		try {
			Thread.sleep(seconds * 1000);
		} catch (InterruptedException e) {

		}
	}

	@SuppressWarnings("unchecked")
	public static String orderLog(long sub_request_id, long account_number) {
		return StringUtils.join("SR[", sub_request_id, "] Account Number[",
				account_number, "],");
	}

	public static Timestamp parseReceivedTime(String received_time)
			throws ParseException {
		Date recievedDate = null;
		Timestamp timeStampDate = null;
		SimpleDateFormat recivedDateFormat = new SimpleDateFormat(
				"dd-MM-yyyy HH:mm:ss SSS");
		recievedDate = recivedDateFormat.parse(received_time);
		timeStampDate = new Timestamp(recievedDate.getTime());

		return timeStampDate;
	}

	public static HashMap<String, String> getCommaSeparatedAsHashMap(String str) {

		HashMap<String, String> hashed = new HashMap<String, String>();
		if (str == null || str.length() < 1) {
			return hashed;
		}

		String temp[] = str.split(",");
		if (temp != null && temp.length > 0) {
			for (int k = 0; k < temp.length; k++) {
				if (temp[k].length() > 2 & temp[k].contains("=")) { // added for the empty
																	// commas
					String attr = temp[k].substring(0, temp[k].indexOf('=')).trim();
					String val = temp[k]
							.substring(temp[k].indexOf('=') + 1, temp[k].length()).trim();
					if (attr != "" && attr.length() > 0) { // added for the empty commas
						hashed.put(attr, val);
					}
				}
			}
		}

		return hashed;
	}

	public static HashMap<String, String> getCommaSeparatedStringAsHashMap(String str) {

		HashMap<String, String> hashed = new HashMap<String, String>();
		if (str == null || str.length() < 1) {
			return hashed;
		}

		String temp[] = str.split(",");
		if (temp != null && temp.length > 0) {
			for (int k = 0; k < temp.length; k++) {
				String[] attr = temp[k].trim().split("=");
				if (attr.length == 2 && attr[0] != null && attr[1] != null) {
					hashed.put(attr[0].trim(), attr[1].trim());
				}
			}
		}

		return hashed;
	}

	public static String getDynamicParameter(String parameterName,
			HashMap<String, String> workflowParameters, String workFlowParameterItemStr) {
		String paramValue = null;

		if (workFlowParameterItemStr != null
				&& workFlowParameterItemStr.indexOf(parameterName) >= 0) {

			String[] workFlowParameterItems = workFlowParameterItemStr.split(",");
			for (String workFlowParameterNameValue : workFlowParameterItems) {

				if (workFlowParameterNameValue != null
						&& workFlowParameterNameValue.indexOf("=") >= 0) {

					String[] workFlowParameter = workFlowParameterNameValue.split("=");
					if (workFlowParameter != null && workFlowParameter.length == 2) {

						if (workFlowParameter[0] != null && workFlowParameter[0].trim()
								.equalsIgnoreCase(parameterName)) {

							String parameterValue = workFlowParameter[1];
							if (parameterValue != null
									&& parameterValue.startsWith("$")) {

								// Substring and get the name and get from
								// workflowParameters hashmap
								String paramValueMapName = parameterValue.substring(1,
										parameterValue.length() - 1);
								paramValue = workflowParameters.get(paramValueMapName);
								logger.debug("parameterName[" + parameterName
										+ "], paramValueMapName[" + paramValueMapName
										+ "],paramValue[" + paramValue + "]");
							} else {

								paramValue = parameterValue;
								logger.debug("parameterName[" + parameterName
										+ "],paramValue[" + paramValue + "]");

							}

						}

					}

				}

			}
		}

		return paramValue;
	}

	public static String[] getClassPath(String path) {
		String[] parts;

		if (path != null) {
			parts = path.split(".");
			// parts[1] = parts[1].
			return parts;
		} else {
			return null;
		}
	}

	// template will be something like
	// [oldValue|newvalue,newvalue#oldValue|newvalue#]
	public static List<String> handleMapping(List<String> data, String mapping) {
		Map<String, Object> mappingMap = new HashMap<String, Object>();
		if (Util.isValidObject(mapping)) {
			String[] rps = mapping.split("#");
			for (String rp : rps) {
				String rpCode;
				if (rp.contains("|")) {
					String[] rpDetails = rp.split("\\|");
					rpCode = rpDetails[0];
					String actualValue = rpDetails[1];
					if (actualValue.contains(",")) {
						mappingMap.put(rpCode, actualValue.split(","));
					} else {
						mappingMap.put(rpCode, actualValue);
					}
				}
			}
		}
		List<String> values = new ArrayList<String>();
		if (Util.isValidateCollection(data)) {
			for (String item : data) {
				Object realValue = mappingMap.get(item);
				if (Util.isValidObject(realValue)) {
					if (realValue instanceof String) {
						values.add((String) realValue);
					} else if (realValue instanceof String[]) {
						values.addAll(Arrays.asList((String[]) realValue));
					}
				} else {
					if (Util.isValidObject(item)) {
						values.add(item);
					}
				}
			}
		}
		return values;
	}

	public static HashMap<String, String> parametersAsHashMap(long sub_request_id,
			String parameters, HashMap<String, String> order_information,
			HashMap<String, String> sessionVariables) throws Exception {
		HashMap<String, String> itemParameters = new HashMap<String, String>();

		if (parameters != null) {
			String[] params = parameters.split(",");
			for (int i = 0; i < params.length; i++) {
				if (params[i].startsWith("vars")) {
					String[] keyValue = params[i].split("=");
					if (keyValue != null && keyValue.length > 0) {
						String[] vars = keyValue[1].split(";");
						if (vars != null && vars.length > 0) {
							for (int d = 0; d < vars.length; d++) {
								if (sessionVariables.get(vars[d]) == null
										&& order_information.get(vars[d]) == null) {
									throw new Exception(sub_request_id
											+ ". Item is missing some parameters");
								}
							}
						} else {
							if (sessionVariables.get(keyValue[0]) == null
									&& order_information.get(keyValue[0]) == null) {
								throw new Exception(sub_request_id
										+ ". Item is missing some parameters");
							}
						}
						itemParameters.put("vars", keyValue[1]);
					}
				} else {
					String[] tmp = params[i].split("=");
					if (tmp != null && tmp.length == 2) {
						itemParameters.put(tmp[0], tmp[1]);
					}

				}
			}
		}

		return itemParameters;

	}

	public static int compareCurrentSquenceAndCommitedSequences(long currentSequence,
			String commitedSequences) {
		int result = 0;
		if (commitedSequences != null) {
			String[] patts = commitedSequences.split(",");
			for (int i = 0; i < patts.length; i++) {
				long commitedSeqence = Long.parseLong(patts[i]);
				if (currentSequence < commitedSeqence) {
					return -1;
				} else {
					return 1;
				}
			}
		}

		return result;

	}

	public static String HashMapAsCommaSeperated(HashMap<String, String> hashed) {
		String str = "";

		if (hashed != null) {
			Iterator<String> keys = hashed.keySet().iterator();
			while (keys.hasNext()) {
				String key = (String) keys.next();
				str += key + "=" + hashed.get(key) + ",";
			}

			if (str.endsWith(",")) {
				str = (String) str.subSequence(0, (str.length() - 1));
			}
		}
		return str;
	}

	public static String listAsCommaSeperated(List<String> list) {
		StringBuilder result = new StringBuilder();
		String prefix = "";
		for (String st : list) {
			result.append(prefix);
			result.append(st);
			prefix = ",";
		}
		return result.toString();
	}

	public static String formatAccountNumberAs05String(long accountNumber971) {
		logger.debug("Entering in  formatAccountNumberAs05String and number is: "
				+ accountNumber971);

		String str = String.valueOf(accountNumber971);

		if (str.startsWith("971")) {
			logger.debug("Testing formatAccountNumberAs05String Case 1: " + "0"
					+ str.substring(3));
			return "0" + str.substring(3);
		} else if ((str.length() == 10 || str.length() == 9) && !str.startsWith("5")) {
			logger.debug("Testing formatAccountNumberAs05String Case 2: " + str);
			return str;
		} else {
			logger.debug("Testing formatAccountNumberAs05String Case 3: " + "0" + str);
			return "0" + str;
		}

	}

	/**
	 * This method will format acccount with prefixed By String, first 971 numbers
	 * will be removed fromm account number.
	 * 
	 * @param accountNumber971
	 * @param prefixedBy
	 * @return
	 */
	public static String formatAccountNumberPrefixedBy(long accountNumber971,
			String prefixedBy) {
		ActivitiLoggingUtil.logMessage(Level.DEBUG,
				"Entering in  formatAccountNumberPrefixedBy and number is: "
						+ accountNumber971);
		String str = String.valueOf(accountNumber971);
		String formattedAccNumber;
		if (str.startsWith("971")) {
			formattedAccNumber = prefixedBy + str.substring(3);
			ActivitiLoggingUtil.logMessage(Level.DEBUG,
					"Testing formatAccountNumberPrefixedBy Case 1: "
							+ formattedAccNumber);
		} else {
			formattedAccNumber = prefixedBy + str;
			ActivitiLoggingUtil.logMessage(Level.DEBUG,
					"Testing formatAccountNumberPrefixedBy Case 2: "
							+ formattedAccNumber);
		}
		return formattedAccNumber;
	}

	// 0566109783
	public static String formatAccountNumberAs971String(long accountNumber05) {

		logger.debug("Entering in  formatAccountNumberAs971String and number is: "
				+ accountNumber05);
		String str = String.valueOf(accountNumber05);

		if (str.startsWith("971")) {
			return str;

		}
		// if number starts with "2|3|4|6|7|9" and length 8 then its fixed line. Append
		// 971 and return
		else if (str.matches("^(2|3|4|6|7|9).*") && str.length() == 8) {
			return "971" + str;

		} else if (!str.startsWith("5") && str.length() == 9) {
			return str;

		} else if (!str.startsWith("5") && str.length() == 10) {
			return str;
		}

		logger.debug("Testing formatAccountNumberAs971String Case 3: " + "971" + str);
		return "971" + str;
	}

	public static String formatAccountNumberAs971StringFixed(long accountNumber05) {

		logger.debug("Entering in  formatAccountNumberAs971String and number is: "
				+ accountNumber05);
		String str = String.valueOf(accountNumber05);

		if (str.startsWith("971")) {
			logger.debug("Testing formatAccountNumberAs971String Case 1: " + str);
			return str;

		} else if (str.length() == 8) {
			logger.debug("Testing formatAccountNumberAs971String Case 2: " + str);
			return "971" + str;
		}

		logger.debug("Testing formatAccountNumberAs971String Case 3: " + "971" + str);
		return "971" + str;
	}

	/**
	 * Method to split the given String with specified delimiters
	 * 
	 * 
	 * @param givenString
	 * @param Delimiters
	 * @return
	 */
	public static List<String> stringSplit(String givenString, String Delimiters) {

		// TODO can be moved to UTIL

		StringTokenizer StrTkn = new StringTokenizer(givenString, Delimiters);
		ArrayList<String> subrequestList = new ArrayList<String>(givenString.length());

		while (StrTkn.hasMoreTokens()) {
			subrequestList.add(StrTkn.nextToken());
		}

		return subrequestList;
	}

	public static List<Long> stringSplitToLongList(String givenString,
			String Delimiters) {

		// TODO can be moved to UTIL

		StringTokenizer StrTkn = new StringTokenizer(givenString, Delimiters);
		ArrayList<Long> subrequestList = new ArrayList<Long>(givenString.length());

		while (StrTkn.hasMoreTokens()) {
			subrequestList.add(Long.parseLong(StrTkn.nextToken()));
		}

		return subrequestList;
	}

	public static HashMap<BigDecimal, String> getWorkflowItemTypes() {
		HashMap<BigDecimal, String> itemsTypes = new HashMap<BigDecimal, String>();

		itemsTypes.put(Constants.crmInquiryItemType, "CRM Inquiry");
		itemsTypes.put(Constants.crmOperationItemType, "CRM Operation");
		itemsTypes.put(Constants.eligibilityCheckItemType, "Eligibility Check");
		itemsTypes.put(Constants.networkOperationItemType, "Network Operation");
		itemsTypes.put(Constants.networkInquiryItemType, "Network Inquiry");

		return itemsTypes;
	}

	public static Date getDateFromString(String dateStr, String dateFormat) {
		SimpleDateFormat formatter = new SimpleDateFormat(dateFormat);
		Date date = null;
		try {
			date = formatter.parse(dateStr);
		} catch (ParseException e) {
			e.printStackTrace();
		}
		return date;
	}

	public static boolean isNumeric(String str) {
		return str.matches("-?\\d+(\\.\\d+)?"); // match a number with optional '-' and
												// decimal.
	}

	public static String getMaxDate(List<Date> dates) {
		Collections.sort(dates);
		return new SimpleDateFormat("EEE MMM dd HH:mm:ss z yyyy")
				.format(dates.get(dates.size() - 1));
	}

	public static int countOccurrences(String haystack, char needle) {
		int count = 0;
		for (int i = 0; i < haystack.length(); i++) {
			if (haystack.charAt(i) == needle) {
				count++;
			}
		}
		return count;
	}

	public static boolean compareCurrentDate(String aStartDate, String aExpiryDate) {
		boolean flag = false;
		try {

			DateFormat format = new SimpleDateFormat("EEE MMM dd HH:mm:ss z yyyy");

			Date startDate = format.parse(aStartDate);
			Date expiryDate = format.parse(aExpiryDate);

			Date currentDate = Calendar.getInstance().getTime();

			if (currentDate.compareTo(startDate) >= 0
					&& currentDate.compareTo(expiryDate) <= 0) {
				flag = true;
			} else {
				flag = false;
			}

		} catch (Exception e) {
			flag = false;
		}
		return flag;

	}

	public static int compareDates(String firstDate, String secondDate) {
		int flag = -1;// 0 Equal 1 - First Date Greater than second , 2- Second date
						// Greater than first date
		try {

			logger.debug("firstDate:[" + firstDate + "] seconddate[" + secondDate + "]");
			DateFormat format = new SimpleDateFormat("EEE MMM dd HH:mm:ss z yyyy");

			Date startDate = format.parse(firstDate);
			Date expiryDate = format.parse(secondDate);

			int status = startDate.compareTo(expiryDate);

			if (status == 0) {
				flag = 0;
			} else if (status < 0) {
				flag = 2;
			} else {
				flag = 1;
			}

		} catch (Exception e) {
			logger.error("Exception while compareDates()", e);
		}
		return flag;

	}

	/**
	 * This Function will count total numbers of count of Identifire in the
	 * SourceString
	 * 
	 * @param SourceString - input string
	 * @param identifire   - String to be count
	 * @return
	 */
	public static Integer getIdentifireCount(String SourceString, String identifire) {
		if (SourceString != null && identifire != null) {
			int index = SourceString.indexOf(identifire);
			int count = 0;
			while (index != -1) {
				count++;
				SourceString = SourceString.substring(index + 1);
				index = SourceString.indexOf(identifire);
			}
			return count;
		} else
			return null;
	}

	public static String getStaticParameter(HashMap<String, String> staticParameters,
			Object aKey) {
		String allowedServiceCount = null;
		if (null != staticParameters) {
			allowedServiceCount = staticParameters.get(aKey);
		}
		return allowedServiceCount;
	}

	public static String getMapMessageDetails(MapMessage mapMessage) throws JMSException {
		Enumeration<String> mapNames = mapMessage.getMapNames();
		String messageString = "";
		while (mapNames.hasMoreElements()) {
			String nextElement = mapNames.nextElement();
			messageString = messageString + "Name:[" + nextElement + "],value["
					+ mapMessage.getString(nextElement) + "]";
		}
		return messageString;
	}

	/**
	 * This Function will Calcualte the Prorated amount based on remainind days in
	 * the month
	 * 
	 * @param totalAllowance - The Total Allowance ie 500MB , 250 Min
	 * @return proratedAmount -The calculated prorated amount .
	 */

	public static double calculateProratedAmount(BigDecimal totalAllowance) {

		Calendar cal = Calendar.getInstance();
		int totalDays = cal.getActualMaximum(Calendar.DAY_OF_MONTH);
		int todayDay = cal.get(Calendar.DAY_OF_MONTH);
		int remainingDays = totalDays - todayDay + 1; // Added + 1 for including current
														// day also in calculation
		BigDecimal proratedAmount = new BigDecimal(0);
		if (totalDays == remainingDays) {
			proratedAmount = totalAllowance;
		} else if (remainingDays == 0) {
			proratedAmount = new BigDecimal(0);
		} else {
			double proratedValue = (totalAllowance.doubleValue() * remainingDays)
					/ new Float(30);
			proratedAmount = new BigDecimal(proratedValue);
		}
		double calculate = proratedAmount.doubleValue() / 100;
		calculate = Math.ceil(calculate) * 100;
		return calculate;
	}

	public static String checkComparisonCondition(String[] conditions,
			HashMap<String, String> checkAgainstMap) {
		String failureReason = new String();
		for (String condition : conditions) {
			// if equals conditions
			if (condition.contains("=")) {
				String cond[] = condition.split("=");
				if (checkAgainstMap.get(cond[0]) == null
						|| !checkAgainstMap.get(cond[0]).equals(cond[1])) {
					failureReason = "checkAgainstMap.get(" + cond[0] + ")["
							+ checkAgainstMap.get(cond[0])
							+ "] Not Macting checkAgainstMap.get(" + cond[0] + ")["
							+ checkAgainstMap.get(cond[0]) + "]";
				}

			} else if (condition.contains(">")) {
				String cond[] = condition.split(">");
				if (checkAgainstMap.containsKey(cond[0])
						&& checkAgainstMap.get(cond[0]) != null) {
					long valueFromOrderInformation = Long
							.parseLong(checkAgainstMap.get(cond[0]));
					long value = Long.parseLong(cond[1]);
					if (!(valueFromOrderInformation > value)) {
						failureReason = "checkAgainstMap.get(" + cond[0] + ")["
								+ checkAgainstMap.get(cond[0])
								+ "] Not Macting greater than checkAgainstMap.get("
								+ cond[0] + ")[" + checkAgainstMap.get(cond[0]) + "]";
						break;
					}
				} else {
					failureReason = "checkAgainstMap.get(" + cond[0] + ")["
							+ checkAgainstMap.get(cond[0])
							+ "] Not Macting greater than checkAgainstMap.get(" + cond[0]
							+ ")[" + checkAgainstMap.get(cond[0]) + "]";
					break;
				}
			} else if (condition.contains("!=")) {
				String cond[] = condition.split("!=");
				if (checkAgainstMap.containsKey(cond[0])
						&& checkAgainstMap.get(cond[0]) != null) {
					String valueFromOrderInformation = checkAgainstMap.get(cond[0]);
					String value = cond[1];
					if (null != valueFromOrderInformation) {
						if (valueFromOrderInformation.equalsIgnoreCase(value))
							failureReason = "checkAgainstMap.get(" + cond[0] + ")["
									+ checkAgainstMap.get(cond[0])
									+ "] Not Macting != checkAgainstMap.get(" + cond[0]
									+ ")[" + checkAgainstMap.get(cond[0]) + "]";
						break;
					}
				} else {
					failureReason = "checkAgainstMap.get(" + cond[0] + ")["
							+ checkAgainstMap.get(cond[0])
							+ "] Not Macting != checkAgainstMap.get(" + cond[0] + ")["
							+ checkAgainstMap.get(cond[0]) + "]";
					break;
				}
			} else {
				failureReason = "unsuported comparison operation";
				break;
			}
		}

		return failureReason;
	}

	public static Long addNumbers(List<Long> numbers) {

		Long value = new Long(0);

		if (numbers != null && numbers.size() != 0) {

			for (Long param : numbers) {

				value = value + param;

			}
		}
		return value;
	}

	public static Long multiplyNumbers(List<Long> numbers) {

		Long value = 1l;

		if (numbers != null && numbers.size() != 0) {

			for (Long param : numbers) {

				value = value * param;

			}

		}
		return value;
	}

	public static String getStringFromDate(Date date, String dateFormat) {
		SimpleDateFormat formatter = new SimpleDateFormat(dateFormat);
		return formatter.format(date);
	}

	public static <T> List<T> intersection(Collection<T> list1, Collection<T> list2) {
		List<T> list = new ArrayList<T>();

		for (T t : list1) {
			if (list2.contains(t)) {
				list.add(t);
			}
		}

		return list;
	}

	/**
	 * Converts an object into JavaBean XML.
	 * 
	 * @throws IOException
	 */
	public static String objectToXml(Object obj) throws IOException {
		String xmlString = "";
		try {
			xmlString = marshal(obj);
		} catch (Exception e) {
			return javaObjectToXml(obj);
		}
		return xmlString;
	}

	public static String javaObjectToXml(Object obj) throws IOException {
		String xml = null;
		if (obj != null) {
			OutputStream baos = new ByteArrayOutputStream();
			XMLEncoder xmlEncoder = new XMLEncoder(baos);
			xmlEncoder.writeObject(obj);
			xmlEncoder.close();
			xml = baos.toString();
			baos.close();
		}
		return xml;
	}

	/**
	 * Converts a JavaBean XML to corresponding object.
	 * 
	 * @throws IOException
	 */
	public static Object xmlToObject(String xml) throws IOException {
		Object obj = null;
		if (xml != null) {
			InputStream is = new ByteArrayInputStream(xml.getBytes());
			XMLDecoder xmlDecoder = new XMLDecoder(is);
			obj = xmlDecoder.readObject();
			is.close();
			xmlDecoder.close();
		}
		return obj;
	}

	/**
	 * Converts a JavaBean XML to corresponding object.
	 * 
	 * @throws IOException
	 */
	public static <T> T xmlToObject(String xml, Class<T> clazz) throws Exception {
		JAXBContext jaxbContext = JAXBContext.newInstance(clazz.getPackage().getName());
		Unmarshaller jaxbUnmarshaller = jaxbContext.createUnmarshaller();
		StringReader reader = new StringReader(xml);
		T customer = (T) jaxbUnmarshaller.unmarshal(reader);
		return customer;
	}

	public static String collectionAsString(Collection<?> collection,
			CharSequence separator) {

		if (collection.isEmpty()) {
			return "";
		} else {
			StringBuilder sepValueBuilder = new StringBuilder();

			for (Object obj : collection) {
				// Append the valuen and the separator even if it's the las element
				sepValueBuilder.append("'").append(obj).append("'").append(separator);
			}
			// Remove the last separator
			sepValueBuilder.setLength(sepValueBuilder.length() - separator.length() - 1);

			return sepValueBuilder.append("'").toString();

		}
	}

	public static String toAnotherDateFormat(Date date, String format) {
		DateFormat df = new SimpleDateFormat(format);
		return df.format(date);
	}

	public static boolean isValidObject(Object obj) {

		boolean isValid = false;
		if (obj != null && !"".equals(obj)) {
			isValid = true;
		}
		return isValid;
	}

	public static boolean isValidSessionObject(Object obj) {
		boolean isValid = false;
		if (obj != null && !"".equals(obj) && !"null".equalsIgnoreCase(obj.toString())) {
			isValid = true;
		}
		return isValid;
	}

	@SuppressWarnings("rawtypes")
	public static boolean isValidateCollection(Collection collection) {
		boolean isValidList = false;
		if (collection != null && !collection.isEmpty()) {
			isValidList = true;
		}
		return isValidList;
	}

	public static Set<String> prepareAccountNumberList(
			HashMap<String, String> order_information, long account_number) {
		Set<String> accountNumberSet = null;
		String accountNumberAs050 = Util.formatAccountNumberAs05String(account_number);
		if (Util.isValidObject(order_information
				.get(Constants.ORDER_INFORMATION_MAP_KEY_REREGISTER_ACCOUNT_NUMBER))) {
			String accountIdsCommaSeparated = "";
//			if(order_information.get(Constants.ORDER_INFORMATION_MAP_KEY_REREGISTER_ACCOUNT_NUMBER).contains(accountNumberAs050)){
			accountIdsCommaSeparated = order_information
					.get(Constants.ORDER_INFORMATION_MAP_KEY_REREGISTER_ACCOUNT_NUMBER);
//			}else{
//				accountIdsCommaSeparated=order_information.get(Constants.ORDER_INFORMATION_MAP_KEY_REREGISTER_ACCOUNT_NUMBER)+";"+accountNumberAs050;
//			}
			String[] accountNumbersArray = accountIdsCommaSeparated.split(";");
			List<String> accountNumberList = Arrays.asList(accountNumbersArray);
			accountNumberSet = new HashSet<String>(accountNumberList);
		} else {
			accountNumberSet = new HashSet<String>();
			accountNumberSet.add("" + accountNumberAs050);
		}
		return accountNumberSet;
	}

	public static Date modifiyDateWithInterval(Date date, int interval,
			int intervalType) {
		Calendar cal = Calendar.getInstance();
		cal.setTime(date);
		cal.add(intervalType, interval);
		return cal.getTime();
	}

	public static byte[] objectToByteArray(Object request) {

		byte[] recievedRequest = null;

		try {
			ByteArrayOutputStream bos = new ByteArrayOutputStream();
			ObjectOutputStream oos = new ObjectOutputStream(bos);

			oos.writeObject(request);
			oos.flush();
			oos.close();
			bos.close();

			recievedRequest = bos.toByteArray();

		} catch (Exception e) {
			logger.error("Exception: ", e);
		}

		return recievedRequest;

	}

	/**
	 * Method which marshals the given object to XML.
	 */
	@SuppressWarnings("unchecked")
	public static <T> String marshal(T obj) throws JAXBException {
		StringWriter sw = new StringWriter();
		if (obj != null) {
			JAXBContext context = JAXBContext.newInstance(obj.getClass());
			Marshaller marshaller = context.createMarshaller();
			marshaller.setProperty(Marshaller.JAXB_FORMATTED_OUTPUT, true);
//			JAXBElement<T> rootElement = new JAXBElement<T>(new QName(obj.getClass().getSimpleName().toLowerCase()), (Class<T>) obj.getClass(), obj);
			marshaller.marshal(obj, sw);
			logger.debug("Marshalled the object succesfully");
		}
		return sw.toString();
	}

	/**
	 * Method which unmarshals the given XML to the corresponding object.
	 */
	@SuppressWarnings("unchecked")
	public static <T> T unmarshal(String xml, Class<T> target)
			throws JAXBException, ClassCastException {
		T object = null;
		if (xml != null && !xml.trim().isEmpty()) {
			System.out.println(target.getCanonicalName());
			JAXBContext context = JAXBContext.newInstance(target);
			Unmarshaller unmarshaller = context.createUnmarshaller();
			object = (T) unmarshaller.unmarshal(new ByteArrayInputStream(xml.getBytes()));
			logger.debug("Unmarshalled the XML succesfully");
		}
		return object;
	}

	// deep copy Serializable object
	public static Serializable deepCopyObject(Serializable object) {

		try {
			ByteArrayOutputStream baos = new ByteArrayOutputStream();
			ObjectOutputStream oos = new ObjectOutputStream(baos);
			oos.writeObject(object);

			ByteArrayInputStream bais = new ByteArrayInputStream(baos.toByteArray());
			ObjectInputStream ois = new ObjectInputStream(bais);
			Serializable deepCopyObject = (Serializable) ois.readObject();
			ois.close();
			oos.close();
			return deepCopyObject;

		} catch (Exception e) {
			logger.error("error happened while deepCopy object ", e);
			return null;
		}
	}

	/**
	 * @return current time stamp
	 */
	public static Timestamp getCurrentTimestamp() {
		return new Timestamp(System.currentTimeMillis());
	}

	/**
	 * Checks whether the given collection is null or not.
	 */
	public static boolean isCollectionNotEmpty(Collection<?> coll) {
		return coll != null && !coll.isEmpty();
	}

	/**
	 * returns true if the collection passed is empty/null.
	 */
	public static boolean isCollectionEmpty(Collection<?> coll) {
		return !isCollectionNotEmpty(coll);
	}

	/**
	 * <pre>
	 * <b>Description : </b>
	 * Gives a human readable text for on the given text.
	 * 
	 * </pre>
	 */
	public static String toHumanReadableText(String text) {
		String humanReadableText = null;
		logger.debug("Converting '" + text + "' to human readable format");
		if (text != null && !text.trim().isEmpty()) {
			try {
				return new String(text.getBytes("ISO-8859-15"));
			} catch (UnsupportedEncodingException e) {
				logger.error("Error in converting string to human readable format", e);
			}
		}
		logger.debug("Human readable text: " + humanReadableText);
		return humanReadableText;
	}

	/**
	 * <pre>
	 * <b>Description : </b>
	 * Checks whether the given array is empty or not.
	 * 
	 * </pre>
	 */
	public static <T> boolean isArrayNotEmpty(T[] array) {
		return array != null && array.length > 0;
	}

	/**
	 * <pre>
	 * <b>Description : </b>
	 * Adds all the elements of the given array to the given collection.
	 * 
	 * </pre>
	 */
	public static <T> void addAll(Collection<T> collection, T[] array) {
		for (int i = 0; i < array.length; i++) {
			collection.add(array[i]);
		}
	}

	private Map<String, BigDecimal> fillIdentityTypeMap() {
		// TODO Auto-generated method stub
		Map<String, BigDecimal> idenitiyTypeMap = new HashMap<String, BigDecimal>();
		idenitiyTypeMap.put("PA", new BigDecimal(4));
		idenitiyTypeMap.put("UC", new BigDecimal(1));
		idenitiyTypeMap.put("GI", new BigDecimal(68));

		return idenitiyTypeMap;
	}

	/**
	 * This method to log all network request and response and keep in log the
	 * following : 1-subrequestId (EX:123654785) 2-accountNaumber (Ex : 0506589555)
	 * 3-clazz 4-messageType (EX : Request or Response) 5-logMessage (EX : <XML>
	 * format)
	 * 
	 **/

	public static void logNetworkInteractions(long subRequestId, String accountNaumber,
			Class clazz, String messageType, Object logMessage) {
		long start = System.currentTimeMillis();
		StringBuilder builder = new StringBuilder();
		String xmlLogMessage = null;
		try {
			xmlLogMessage = Util.marshal(logMessage);
		} catch (JAXBException e) {
			xmlLogMessage = e.getMessage();
		}
		builder.append("ID:");
		builder.append(subRequestId);
		builder.append(":");
		builder.append(accountNaumber);
		builder.append(":");
		builder.append(clazz.getSimpleName());
		builder.append("\n");
		builder.append(messageType);
		builder.append(":::\n");
		builder.append(xmlLogMessage);

		networkLogger.info(builder.toString());
		networkLogger.info(clazz.getSimpleName() + " done in "
				+ (System.currentTimeMillis() - start) + " milliseconds");

	}

	/**
	 * This method to log all network request and response and keep in log the
	 * following : 1-subrequestId (EX:123654785) 2-accountNaumber (Ex : 0506589555)
	 * 3-clazz 4-messageType (EX : Request or Response) 5-logMessage (EX : <XML>
	 * format)
	 * 
	 **/
	public static void logNetworkInteractionString(long subRequestId,
			String accountNaumber, Class clazz, String messageType,
			String xmlLogMessage) {
		long start = System.currentTimeMillis();
		StringBuilder builder = new StringBuilder();

		builder.append("ID:");
		builder.append(subRequestId);
		builder.append(":");
		builder.append(accountNaumber);
		builder.append(":");
		builder.append(clazz.getSimpleName());
		builder.append("\n");
		builder.append(messageType);
		builder.append(":::\n");
		builder.append(xmlLogMessage);

		networkLogger.info(builder.toString());
		networkLogger.info(clazz.getSimpleName() + " done in "
				+ (System.currentTimeMillis() - start) + " milliseconds");

	}

	public static List<BigDecimal> stringSplitToBigDecimalList(String givenString,
			String delimiter) {

		StringTokenizer StrTkn = new StringTokenizer(givenString, delimiter);
		ArrayList<BigDecimal> subrequestList = new ArrayList<BigDecimal>(
				givenString.length());

		while (StrTkn.hasMoreTokens()) {
			subrequestList.add(new BigDecimal(StrTkn.nextToken()));
		}

		return subrequestList;
	}

	public static String serializeDBOSessionVarHashMap(
			HashMap<String, String> sessionVarsParam) {

		String sessionVarsSerialized = null;
		if (null != sessionVarsParam && sessionVarsParam.isEmpty() == false) {
			DBOSessionVariables sessionVars = new DBOSessionVariables();
			sessionVars.setSessionVariables(sessionVarsParam);
			sessionVarsSerialized = Serializer.serialize(sessionVars);
		}
		return sessionVarsSerialized;
	}

	public static String calculateDataInBytes(String attributeValue, String uom) {
		if (!isValidObject(attributeValue) || !isValidObject(uom))
			return null;

		double result = 1d;
		if (uom.equalsIgnoreCase("TB")) {
			result = Double.valueOf(attributeValue) * 1000 * 1000 * 1000 * 1024;
		} else if (uom.equalsIgnoreCase("GB")) {
			result = Double.valueOf(attributeValue) * 1000 * 1000 * 1024;
		} else if (uom.equalsIgnoreCase("MB")) {
			result = Double.valueOf(attributeValue) * 1000 * 1024;
		} else if (uom.equalsIgnoreCase("KB")) {
			result = Double.valueOf(attributeValue) * 1024;
		} else {
			result = Long.parseLong(attributeValue);
		}

		long integerPart = (long) result;
		double fractionPart = result - integerPart;

		String totalFreebiesString = "" + integerPart;
		if (fractionPart > 0) {
			String fractionPartAsString = "" + fractionPart;
			totalFreebiesString = totalFreebiesString
					+ fractionPartAsString.substring(fractionPartAsString.indexOf("."));
		}
		logger.debug("total freebiee " + totalFreebiesString);

		return totalFreebiesString;
	}

	public static String calculateDataInKBytes(String attributeValue, String uom) {
		if (!isValidObject(attributeValue) || !isValidObject(uom))
			return null;

		double result = 1d;
		if (uom.equalsIgnoreCase("TB")) {
			result = Double.valueOf(attributeValue) * 1000 * 1000 * 1024;
		} else if (uom.equalsIgnoreCase("GB")) {
			result = Double.valueOf(attributeValue) * 1000 * 1024;
		} else if (uom.equalsIgnoreCase("MB")) {
			result = Double.valueOf(attributeValue) * 1024;
		} else {
			result = Long.parseLong(attributeValue);
		}

		long integerPart = (long) result;
		double fractionPart = result - integerPart;

		String totalFreebiesString = "" + integerPart;
		if (fractionPart > 0) {
			String fractionPartAsString = "" + fractionPart;
			totalFreebiesString = totalFreebiesString
					+ fractionPartAsString.substring(fractionPartAsString.indexOf("."));
		}
		logger.debug("total freebiee " + totalFreebiesString);

		return totalFreebiesString;
	}

	public static String getValueInSec(String attributeValue, String uom) {
		Long result = 1L;
		if (uom.equalsIgnoreCase("MINS")) {
			result = Long.valueOf(attributeValue) * 60;
		} else if (uom.equalsIgnoreCase("DAYS")) {
			result = Long.valueOf(attributeValue) * 24 * 60 * 60;
		}
		return String.valueOf(result);
	}

	public static String getValueInHour(String attributeValue, String uom) {
		Float result = 1F;
		if(uom.equalsIgnoreCase("SECONDS")) {
			result = Float.valueOf(attributeValue) / 3600;
		} else if (uom.equalsIgnoreCase("MINS")) {
			result = Float.valueOf(attributeValue) / 60;
		} else if (uom.equalsIgnoreCase("DAYS")) {
			result = Float.valueOf(attributeValue) * 24;
		} 
		return String.valueOf(result);
	}

	public static Object getXpathValue(String xpathString, String value)
			throws XPathExpressionException {
		XPathFactory xpathFactory = XPathFactory.newInstance();
		XPath xpath = xpathFactory.newXPath();
		InputSource source = new InputSource(new StringReader(value));
		Object result = xpath.evaluate(xpathString, source, XPathConstants.NODE);
		return result;
	}

	public static String nodeToString(Node node) throws TransformerException {
		StringWriter buf = new StringWriter();
		Transformer xform = TransformerFactory.newInstance().newTransformer();
		xform.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "yes");
		xform.transform(new DOMSource(node), new StreamResult(buf));
		return (buf.toString());
	}

	// Method to validate whether Input is valid mobile Number
	public static boolean isValidUAEMobNumber(String msisdn) {
		logger.debug("Validating UAEMobNumber [" + msisdn + "]");
		boolean isValid = false;
		if (msisdn != null && Util.isNumeric(msisdn)) {
			int size = msisdn.length();
			if (msisdn.startsWith("00971")) {
				if (size == 14 || size == 13) {
					return true;
				}
			} else if (msisdn.startsWith("971")) {
				if (size == 12 || size == 11) {
					return true;
				}
			} else if (msisdn.startsWith("05")) {
				if (size == 10) {
					return true;
				}
			} else if (msisdn.startsWith("0")) {
				if (size == 9) {
					return true;
				}
			} else if (msisdn.startsWith("+971")) {
				if (size == 13 || size == 12) {
					return true;
				}
			}

		}
		logger.debug("isValidUAEMobNumber - isValid [" + isValid + "]");
		return isValid;
	}

	// Method to validate email address format
	public static boolean isValidEmail(String emailAddress) {

		String EMAIL_PATTERN = "^[_A-Za-z0-9-\\+]+(\\.[_A-Za-z0-9-]+)*@"
				+ "[A-Za-z0-9-]+(\\.[A-Za-z0-9]+)*(\\.[A-Za-z]{2,})$";

		Pattern pattern = Pattern.compile(EMAIL_PATTERN);
		Matcher matcher = pattern.matcher(emailAddress);

		return matcher.matches();
	}

	/**
	 * <pre>
	 * <b>Description : </b>
	 * Gives the list of strings matching the given pattern from the given source.
	 * 
	 * &#64;return
	 * </pre>
	 */
	public static List<String> getQueryParams(String source, String queryParamPattern) {
		List<String> queryParams = new ArrayList<String>();
		Pattern pattern = Pattern.compile(queryParamPattern);
		Matcher matcher = pattern.matcher(source);
		while (matcher.find()) {
			queryParams.add(matcher.group(0));
		}
		return queryParams;
	}

	public static String createEmailBody(HashMap<String, Object> content) {
		String TIBCO_EMAILS_MESSAGE_BODY_DYNAMIC_VALUE = "@";
		String emailBody = null;
		ActivitiLoggingUtil.logMessage(Level.DEBUG, "createEmailBody method  ... ");
		if (content.containsKey("type")) {
			if (content.get("type") != null && content.get("type").equals("html")) {
				emailBody = (String) content.get("message");
				ActivitiLoggingUtil.logMessage(Level.DEBUG, " emailBody>>> " + emailBody);
				Iterator<String> keys = content.keySet().iterator();
				while (keys.hasNext()) {
					String key = (String) keys.next();
					if (emailBody.contains(TIBCO_EMAILS_MESSAGE_BODY_DYNAMIC_VALUE + key
							+ TIBCO_EMAILS_MESSAGE_BODY_DYNAMIC_VALUE)) {
						emailBody = emailBody.replaceAll(
								TIBCO_EMAILS_MESSAGE_BODY_DYNAMIC_VALUE + key
										+ TIBCO_EMAILS_MESSAGE_BODY_DYNAMIC_VALUE,
								(String) content.get(key));
					}
				}
			}
		}
		return emailBody;

	}

	public static String formatDateToString(Date date, String format, String timeZone) {
		// null check
		if (date == null)
			return null;
		// create SimpleDateFormat object with input format
		SimpleDateFormat sdf = new SimpleDateFormat(format);
		// default system timezone if passed null or empty
		if (timeZone == null || "".equalsIgnoreCase(timeZone.trim())) {
			timeZone = Calendar.getInstance().getTimeZone().getID();
		}
		// set timezone to SimpleDateFormat
		sdf.setTimeZone(TimeZone.getTimeZone(timeZone));
		// return Date in required format with timezone as String
		return sdf.format(date);
	}

	/**
	 * This method used to get the property value from given object
	 * 
	 * @param object
	 * @param propertyName
	 * @return
	 */
	public static Object getValue(Object object, String propertyName) {

		if (object == null) {
			throw new IllegalArgumentException(
					"Interspective Object should exist.[class object == null]");
		}

		if (propertyName == null) {
			throw new IllegalArgumentException(
					"Object property is missing. [class property == null]");
		}

		Object fieldValue = null;
		try {// case insensitive declared field search

			Field field = object.getClass().getDeclaredField(findField(propertyName));

			if (field != null) {
				field.setAccessible(true);
				fieldValue = field.get(object);
			}
		} catch (Exception exception) {
			ActivitiLoggingUtil.logMessage(exception);
		}
		return fieldValue;
	}

	/**
	 * This method used to make field name from given expected property
	 * 
	 * @param expectedProperty
	 * @return
	 */
	private static String findField(String expectedProperty) {
		if (StringUtils.isBlank(expectedProperty) && expectedProperty.length() > 1) {
			return expectedProperty;
		}
		expectedProperty = expectedProperty.trim();
		return String.valueOf(expectedProperty.charAt(0)).toLowerCase()
				+ expectedProperty.substring(1);
	}

	/**
	 * This method used to make field name from given expected property
	 * 
	 * @param expectedProperty
	 * @return
	 */
	private static String findProperty(String operation, String expectedProperty) {
		if (StringUtils.isBlank(expectedProperty) && expectedProperty.length() > 1) {
			return expectedProperty;
		}
		expectedProperty = expectedProperty.trim();
		return operation.concat(String.valueOf(expectedProperty.charAt(0)).toUpperCase()
				+ expectedProperty.substring(1));
	}

	/**
	 * This method used to get the property value from given object
	 * 
	 * @param object
	 * @param propertyName
	 * @return
	 */
	public static void setValue(Object object, String propertyName, Object value) {

		if (object == null) {
			throw new IllegalArgumentException(
					"Interspective Object should exist.[class object == null]");
		}

		if (propertyName == null) {
			throw new IllegalArgumentException(
					"Object property is missing. [class property == null]");
		}

		try { // case insensitive declared field search
			Method method = object.getClass().getDeclaredMethod(
					findProperty("set", propertyName), new Class[] { value.getClass() });

			if (method != null) {
				method.invoke(object, value);
			}
		} catch (Exception exception) {
			ActivitiLoggingUtil.logMessage(exception);
		}
	}

	/**
	 * Convert an exception to a String with full stack trace
	 * 
	 * @param ex the exception
	 * @return a String with the full stacktrace error text
	 */
	public static String getExceptionToString(Throwable ex) {
		if (ex == null) {
			return "";
		}
		StringWriter str = new StringWriter();
		PrintWriter writer = new PrintWriter(str);
		try {
			ex.printStackTrace(writer);
			return str.getBuffer().toString();
		} finally {
			try {
				str.close();
				writer.close();
			} catch (IOException e) {
				// ignore
			}
		}
	}

	public static BigDecimal getValidBigDecimal(Object obj) {

		BigDecimal bigDecimal = null;
		if (obj != null) {
			if (obj instanceof Long)
				bigDecimal = BigDecimal.valueOf((Long) obj);
			else if (obj instanceof Double)
				bigDecimal = BigDecimal.valueOf((Double) obj);
			else if (obj instanceof Float)
				bigDecimal = BigDecimal.valueOf((Float) obj);
			else if (obj instanceof Integer)
				bigDecimal = BigDecimal.valueOf((Integer) obj);
			else if (obj instanceof String)
				bigDecimal = new BigDecimal((String) obj);
		}
		return bigDecimal;
	}

	public static Long getValidLong(Object obj) {
		Long val = null;
		if (obj != null) {
			try {
				String temp = (String) obj;
				if (temp.indexOf(".") > -1) {
					Float x = Float.parseFloat(temp);
					val = x.longValue();
				} else {
					val = Long.valueOf(temp);
				}
			} catch (Exception e) {
				e.printStackTrace();
			}
		}
		return val;
	}

	public static HttpMethod getHttpMethod(String httpMethod) {
		if ("delete".equalsIgnoreCase(httpMethod)) {
			return HttpMethod.DELETE;
		}
		if ("get".equalsIgnoreCase(httpMethod)) {
			return HttpMethod.GET;
		}
		if ("head".equalsIgnoreCase(httpMethod)) {
			return HttpMethod.HEAD;
		}
		if ("options".equalsIgnoreCase(httpMethod)) {
			return HttpMethod.OPTIONS;
		}
		if ("patch".equalsIgnoreCase(httpMethod)) {
			return HttpMethod.PATCH;
		}
		if ("post".equalsIgnoreCase(httpMethod)) {
			return HttpMethod.POST;
		}
		if ("put".equalsIgnoreCase(httpMethod)) {
			return HttpMethod.PUT;
		}
		if ("trace".equalsIgnoreCase(httpMethod)) {
			return HttpMethod.TRACE;
		}
		return null;
	}

	/**
	 * Method to parse String date to DATE object<br/>
	 * 
	 * Input:<br/>
	 * dateString - Input date<br/>
	 * dateFormats - Supported Date formats<br/>
	 * 
	 * @param dateString
	 * @param dateFormats
	 * @return
	 */
	public static Date parseDateString(String dateString, String[] dateFormats) {
		Date date = null;
		for (String formatString : dateFormats) {
			try {
				return new SimpleDateFormat(formatString).parse(dateString);
			} catch (ParseException e) {
			}
		}
		return null;
	}

	public static boolean isValidateMap(Map map) {
		boolean isValidList = false;
		if (map != null && !map.isEmpty()) {
			isValidList = true;
		}
		return isValidList;
	}

	public static HashMap<String, String> getSettingsAsHashMap(
			List<ActivitiSetting> settings) {
		HashMap<String, String> map = new HashMap<String, String>();
		for (int i = 0; i < settings.size(); i++) {
			ActivitiSetting setting = settings.get(i);
			map.put(setting.getSettingAttribute(), setting.getSettingValue());
		}
		return map;
	}

	/**
	 * This method used to log network interactions for any status (success/failure)
	 * 
	 * @param configUrl
	 * @param request
	 * @param response
	 * @param requestTime
	 * @param responseTime
	 * @param execution
	 * @param targetSystem
	 * @param status       -- this status is either S or F where S for success, F
	 *                     for failed
	 * @return
	 */
	public static ActivitiNetworkAudit getActivitiNetworkAuditInteractionObj(
			String configUrl, byte[] request, byte[] response, Timestamp requestTime,
			Timestamp responseTime, DelegateExecution execution, String targetSystem,
			String status) {
		String isLoggingEnabled = Config.settings.get(configUrl);
		if ("true".equalsIgnoreCase(isLoggingEnabled)) {
			ActivitiNetworkAudit actNetworkAuditing = new ActivitiNetworkAudit();
			actNetworkAuditing.setAuditRequest(request);
			actNetworkAuditing.setRequestTime(requestTime);
			actNetworkAuditing.setTargetSystem(targetSystem);
			actNetworkAuditing.setProcessInstanceId(execution.getProcessInstanceId());
			actNetworkAuditing.setExecutionId(execution.getId());
			actNetworkAuditing.setAuditResponse(response);
			actNetworkAuditing.setResponseTime(responseTime);
			actNetworkAuditing.setBusinessId(Objects
					.toString(execution.getVariable(Constants.APP_REQ_ID_VAR_NAME)));
			actNetworkAuditing.setStatus(status);
			return actNetworkAuditing;
		}
		return null;
	}

	public static Map<String, String> populateDTORequiredInfo(
			HashMap<String, Object> mediationParams, String jsonRepresentationString,
			Map<String, Object> sessionParams) {
		Map<String, String> dtoInfoMap = new HashMap<String, String>();
		List<String> ignoredAllowencesSubType = new ArrayList<String>();
		for (String key : mediationParams.keySet()) {
			ActivitiLoggingUtil.logMessage(org.apache.logging.log4j.Level.DEBUG,
					"keyName " + key + " json path " + mediationParams.get(key));
			if (Util.isValidObject(mediationParams.get(key))) {
				if (key.endsWith("Mapping") || key.endsWith("_mapping"))
					continue;

				String path = mediationParams.get(key).toString();
				String value = null;
				String[] pathSplitArr = null;
				String pathType = null;
				String splitHashArr[] = null;
				String splitSemiColonArr[] = null;
				String valuesToReplaceArr[] = null;
				if (path.contains("|")) {
					pathSplitArr = path.split("\\|");

					for (String pathStr : pathSplitArr) {
						valuesToReplaceArr = null;
						if (pathStr.contains("=")) {
							String[] originalPathArr = pathStr.split("=");
							pathType = originalPathArr[0];
							if (originalPathArr[1].contains(";")) {
								splitSemiColonArr = originalPathArr[1].split(";");
								for (String splitSemiColon : splitSemiColonArr) {
									valuesToReplaceArr = null;
									if (splitSemiColon.contains("#")) {
										splitHashArr = splitSemiColon.split("#");
										Object object = readJsonPath(
												jsonRepresentationString,
												splitHashArr[1]);
										if (Util.isValidObject(object)) {
											value = pathType + ";" + splitHashArr[0] + ";"
													+ object.toString();

											if ((mediationParams
													.containsKey(key + "_mapping")
													&& Util.isValidObject(mediationParams
															.get(key + "_mapping"))
													&& null != value)) {
												valuesToReplaceArr = getCorrespondingValueFromMap(
														mediationParams, key, value);
												if (valuesToReplaceArr.length > 1) {
													value = value.replace(
															valuesToReplaceArr[0],
															valuesToReplaceArr[1]);
												}
											}

											if (dtoInfoMap.get(key) != null) {
												dtoInfoMap.put(key, dtoInfoMap.get(key)
														+ "|" + value);
											} else {
												dtoInfoMap.put(key, value);
											}

										} else {
											if (splitHashArr[1].contains("freebies")) {
												ignoredAllowencesSubType.add(
														pathType + "#" + splitHashArr[0]);
											}
										}
									} else {
										Object object = readJsonPath(
												jsonRepresentationString, splitSemiColon);
										if (Util.isValidObject(object)) {
											value = pathType + ";" + object.toString();
											if ((mediationParams
													.containsKey(key + "_mapping")
													&& Util.isValidObject(mediationParams
															.get(key + "_mapping"))
													&& null != value)) {
												valuesToReplaceArr = getCorrespondingValueFromMap(
														mediationParams, key, value);
												if (valuesToReplaceArr.length > 1) {
													value = value.replace(
															valuesToReplaceArr[0],
															valuesToReplaceArr[1]);
												}
											}
											if (dtoInfoMap.get(key) != null) {
												dtoInfoMap.put(key, dtoInfoMap.get(key)
														+ "|" + value);
											} else {
												dtoInfoMap.put(key, value);
											}

										}

									}
								}

							} else {
								if (originalPathArr[1].contains("#")) {
									splitHashArr = originalPathArr[1].split("#");
									Object object = readJsonPath(jsonRepresentationString,
											splitHashArr[1]);
									if (Util.isValidObject(object)) {
										value = pathType + ";" + splitHashArr[0] + ";"
												+ object.toString();
										if ((mediationParams.containsKey(key + "_mapping")
												&& Util.isValidObject(mediationParams
														.get(key + "_mapping"))
												&& null != value)) {
											valuesToReplaceArr = getCorrespondingValueFromMap(
													mediationParams, key, value);
											if (valuesToReplaceArr.length > 1) {
												value = value.replace(
														valuesToReplaceArr[0],
														valuesToReplaceArr[1]);
											}
										}
										if (dtoInfoMap.get(key) != null) {
											dtoInfoMap.put(key,
													dtoInfoMap.get(key) + "|" + value);
										} else {
											dtoInfoMap.put(key, value);
										}

									}
								} else {
									Object object = readJsonPath(jsonRepresentationString,
											originalPathArr[1]);
									if (Util.isValidObject(object)) {
										value = pathType + ";" + object.toString();
										if ((mediationParams.containsKey(key + "_mapping")
												&& Util.isValidObject(mediationParams
														.get(key + "_mapping"))
												&& null != value)) {
											valuesToReplaceArr = getCorrespondingValueFromMap(
													mediationParams, key, value);
											if (valuesToReplaceArr.length > 1) {
												value = value.replace(
														valuesToReplaceArr[0],
														valuesToReplaceArr[1]);
											}
										}
										if (dtoInfoMap.get(key) != null) {
											dtoInfoMap.put(key,
													dtoInfoMap.get(key) + "|" + value);
										} else {
											dtoInfoMap.put(key, value);
										}

									}

								}

							}
						}

					}
				} else {
					if (path.startsWith("VAL_")) {
						value = path.replace("VAL_", "");
					} else {
						Object object = readJsonPath(jsonRepresentationString, path);
						if (Util.isValidObject(object)) {
							value = object.toString();
						}
					}

					ActivitiLoggingUtil.logMessage(org.apache.logging.log4j.Level.DEBUG,
							"value for path " + path + " is " + value);

					if ((mediationParams.containsKey(key + "Mapping")
							&& Util.isValidObject(mediationParams.get(key + "Mapping"))
							&& null != value)) {
						HashMap<String, String> mapping = Util.getCommaSeparatedAsHashMap(
								mediationParams.get(key + "Mapping").toString());

						String temp = mapping.get(value);

						if (temp != null)
							value = temp;

						ActivitiLoggingUtil.logMessage(
								org.apache.logging.log4j.Level.DEBUG,
								"value after mapping " + path + " is " + value);
					} else if ((mediationParams.containsKey(key + "_mapping")
							&& Util.isValidObject(mediationParams.get(key + "_mapping"))
							&& null != value)) {
						HashMap<String, String> mapping = Util.getCommaSeparatedAsHashMap(
								mediationParams.get(key + "_mapping").toString());

						String temp = mapping.get(value);

						if (temp != null)
							value = temp;

						ActivitiLoggingUtil.logMessage(
								org.apache.logging.log4j.Level.DEBUG,
								"value after mapping " + path + " is " + value);
					}
					dtoInfoMap.put(key, value);
				}
			} else {
				ActivitiLoggingUtil.logMessage(org.apache.logging.log4j.Level.ERROR,
						"keyName " + key + " doesn't have value configured ");
			}
		}
		return dtoInfoMap;
	}

	public static String updateJsonPath(String data, String path, String value)
			throws JSONException {
		JSONObject jsonObject = new JSONObject(data);
		String[] keyPath = path.split("\\.");
		JSONObject json = jsonObject;
		for (int i = 0; i < keyPath.length; i++) {
			String key = keyPath[i];

			if (i < keyPath.length - 1) {
				try {
					json = json.getJSONObject(key);
				} catch (JSONException ex) {
					json.put(key, new HashMap<String, Object>());
					json = json.getJSONObject(key);
				}
			} else {
				json = json.put(key, value);
			}
		}
		return jsonObject.toString();
	}

	public static Object readJsonPath(String jsonStr, String path) {
		Object object = null;
		try {
			object = JsonPath.read(jsonStr, path);
		} catch (Exception e) {
			ActivitiLoggingUtil.logMessage(org.apache.logging.log4j.Level.DEBUG, "path "
					+ path + "was not avialble in provided JSON Igonring the value");
		}
		return object;
	}

	private static String[] getCorrespondingValueFromMap(HashMap<String, Object> mapMT,
			String key, String path) {
		logger.info("getCorrespondingValueFromMap - Start");

		String value = null;
		String valueToreplace = null;
		String values[] = new String[2];

		HashMap<String, String> mapping = Util
				.getCommaSeparatedAsHashMap(mapMT.get(key + "_mapping").toString());

		if (path.contains(";")) {
			String pathInfo[] = path.split(";");
			if (pathInfo.length > 2) {
				value = mapping.get(pathInfo[2]);
				valueToreplace = pathInfo[2];
			} else {
				value = mapping.get(pathInfo[1]);
				valueToreplace = pathInfo[1];
			}
		}

		if (Util.isValidObject(valueToreplace) && Util.isValidObject(value)) {
			values[0] = valueToreplace;
			values[1] = value;
		}

		logger.info("valueToreplace = " + valueToreplace);
		logger.info("value = " + value);

		return values;
	}

	public static Object getDynamicparamValue(Map<String, Object> session_information,
			ActivitiMediationParameter param)
			throws UnknownHostException, ParseException {

		Object value = null;
		if ("$D_NewDate".equals(param.getAttributeValue())) {
			value = new Date();
		} else if ("$D_HostName".equals(param.getAttributeValue())) {
			value = InetAddress.getLocalHost().getHostName();
		} else if ("$D_CurrentTimeMillisecond".equals(param.getAttributeValue())) {
			value = System.currentTimeMillis();
		} else if ("$D_CurrentTimeMillisecondStr".equals(param.getAttributeValue())) {
			value = "" + System.currentTimeMillis();
		}

		else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$S_")) {
			value = session_information.get(param.getAttributeValue().substring(3));
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$INT_")) {

			if (param.getAttributeValue().substring(5).startsWith("$S_")) {
				if (null != session_information
						.get(param.getAttributeValue().substring(5).substring(3))) {
					value = Integer.valueOf((String) session_information
							.get(param.getAttributeValue().substring(5).substring(3)));
				}
			} else if (!param.getAttributeValue().substring(5).startsWith("$O_")) {
				value = Integer.valueOf(param.getAttributeValue().substring(5));
			}

			// added by Anwar to add string; //no need but keep for future use
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$STR_")) {

			if (param.getAttributeValue().substring(5).startsWith("$S_")) {
				if (null != session_information
						.get(param.getAttributeValue().substring(5).substring(3))) {
					value = String.valueOf(session_information
							.get(param.getAttributeValue().substring(5).substring(3)));
				}
			} else if (!param.getAttributeValue().substring(5).startsWith("$O_")) {
				value = String.valueOf(param.getAttributeValue().substring(5));
			}

		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$BOOLEAN_")) {
			value = Boolean.valueOf(param.getAttributeValue().substring(9));
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$DOU_")) {
			String substr = param.getAttributeValue().substring(5);
			if (substr != null && substr.startsWith("$S_")) {
				if (null != session_information.get(substr.substring(3))) {
					value = Double.valueOf(
							(String) session_information.get(substr.substring(3)));
				} else {
					value = Double.valueOf(0);
				}
			} else {
				value = Double.valueOf(substr);
			}
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$SHO_")) {
			value = Short.valueOf(param.getAttributeValue().substring(5));
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$DATE_")) {
			if (param.getAttributeValue().substring(6) != null) {
				if (param.getAttributeValue().substring(6) != null
						&& param.getAttributeValue().substring(6).startsWith("$S_")) {

					String[] pats = param.getAttributeValue().substring(6).substring(3)
							.split("\\$");
					DateFormat df = new SimpleDateFormat(pats[0]);
					// checking null exception -- added by Anwar on 15/02/2016
					if (Util.isValidObject(session_information.get(pats[1]))) {
						value = df.parse((String) session_information.get(pats[1]));
					}
				} else {
					String[] pats = param.getAttributeValue().substring(6).split("\\$");
					DateFormat df = new SimpleDateFormat(pats[0]);
					value = df.parse(pats[1]);
				}
			} else {
				value = Integer.valueOf(param.getAttributeValue().substring(5));
			}
		}
		// Below check will always return Date in string format given as in a specified
		// format
		else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$FORMATDATE_")) {
			if (param.getAttributeValue().substring(12) != null) {
				if (param.getAttributeValue().substring(12) != null
						&& param.getAttributeValue().substring(12).startsWith("$S_")) {
					String[] pats = param.getAttributeValue().substring(12).substring(3)
							.split("\\$");
					if (pats != null && pats.length == 3) {
						ActivitiLoggingUtil.logMessage(Level.DEBUG,
								"OLD DATE FORMATE = " + pats[0]);
						DateFormat df1 = new SimpleDateFormat(pats[0]);

						if (isValidSessionObject(session_information.get(pats[1]))) {
							ActivitiLoggingUtil.logMessage(Level.DEBUG,
									"NEW DATE FORMATE = " + pats[2]);
							ActivitiLoggingUtil.logMessage(Level.DEBUG,
									"DATE VALUE = " + session_information.get(pats[1]));
							value = df1.parse((String) session_information.get(pats[1]));
							DateFormat df2 = new SimpleDateFormat(pats[2]);
							value = df2.format(value);
						}
						return value;
					} else {
						// Check if not present in session information
						if (Util.isValidObject(session_information.get(pats[1]))) {
							DateFormat df = new SimpleDateFormat(pats[0]);
							value = df.format(
									df.parse((String) session_information.get(pats[1])));
						}

					}
				}
				if (param.getAttributeValue().substring(12) != null
						&& param.getAttributeValue().substring(12).startsWith("$DF_")) {

					String[] pats = param.getAttributeValue().substring(12).substring(4)
							.split("\\$");
					DateFormat df = new SimpleDateFormat(pats[0]);
					ActivitiMediationParameter newParam = new ActivitiMediationParameter();
					if (pats != null && pats.length == 2) {
						newParam.setAttributeValue(((String) "$" + pats[1])); // Setting
																				// the
																				// second
																				// pats
																				// object
																				// from as
																				// the new
																				// parameter
						// It has been assumed that getDynamicparamValue always return
						// Date object
						value = df.format(
								getDynamicparamValue(session_information, newParam));

					} else if (pats != null && pats.length > 2) {
						String patString = "";
						for (int i = 1; i < pats.length; i++) {

							patString = patString + "$" + pats[i];

						}
						newParam.setAttributeValue(patString);
						value = df.format(
								getDynamicparamValue(session_information, newParam));

					}
				}
			}
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$RELDATE_")) {

			String substr = param.getAttributeValue().substring(9);
			Calendar newDate = Calendar.getInstance();

			for (String shift : substr.split(";")) {
				String[] pats = shift.split("\\$");

				if (pats != null && pats.length == 2) {
					// eg:Calendar.HOUR - is 10
					int field = Integer.parseInt(pats[0]);
					int amount = Integer.parseInt(pats[1]);
					newDate.add(field, amount);
				}
			}
			value = newDate.getTime();
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$SETDATE_")) {

			String substr = param.getAttributeValue().substring(9);
			Calendar newDate = Calendar.getInstance();

			for (String shift : substr.split(";")) {
				String[] pats = shift.split("\\$");

				if (pats != null && pats.length == 2) {
					// eg:Calendar.HOUR - is 10
					int field = Integer.parseInt(pats[0]);

					if (pats[1].equalsIgnoreCase("MAX")) {

						newDate.set(field, newDate.getActualMaximum(field));
					} else if (pats[1].equalsIgnoreCase("MIN")) {

						newDate.set(field, newDate.getActualMinimum(field));
					} else {
						int amount = Integer.parseInt(pats[1]);
						newDate.set(field, amount);
					}
				}
			}
			value = newDate.getTime();
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$CHANGEDATE_")) {

			String substr = param.getAttributeValue().substring(12);
			Calendar newDate = Calendar.getInstance();
			String dateProcessingLogic = null;

			if (substr.startsWith("$S_")) {
				int endIndex = substr.indexOf("^");
				String dateSubStr = substr.substring(0, endIndex);
				String dateString = (String) session_information
						.get(dateSubStr.substring(3));

				DateFormat format = new SimpleDateFormat("EEE MMM dd HH:mm:ss z yyyy");
				Date parse = format.parse(dateString);
				newDate.setTime(parse);

				substr = substr.split("\\^")[1];
			}

			for (String shift : substr.split(";")) {
				String[] pats = shift.split("\\$");

				if (pats != null && pats.length == 3) {
					// eg:Calendar.HOUR - is 10
					if ("SET".equalsIgnoreCase(pats[0])) {
						int field = Integer.parseInt(pats[1]);

						if (pats[2].equalsIgnoreCase("MAX")) {

							newDate.set(field, newDate.getActualMaximum(field));
						} else if (pats[2].equalsIgnoreCase("MIN")) {

							newDate.set(field, newDate.getActualMinimum(field));
						} else {
							int amount = Integer.parseInt(pats[2]);
							newDate.set(field, amount);
						}
					}
					if ("ADD".equalsIgnoreCase(pats[0])) {
						int field = 0;
						// added by mostafa to support different time intervals.
						if (pats[1].startsWith("S_")) {
							if (null != session_information
									&& session_information
											.containsKey(pats[1].substring(2))
									&& Util.isValidObject(session_information
											.get(pats[1].substring(2)))) {
								String unit = (String) session_information
										.get(pats[1].substring(2));
								if (unit.contains("Hourly"))
									field = Calendar.HOUR_OF_DAY;
								else if (unit.contains("Daily"))
									field = Calendar.DAY_OF_MONTH;
								else if (unit.contains("Weekly"))
									field = Calendar.WEEK_OF_MONTH;
								else if (unit.contains("Monthly"))
									field = Calendar.MONTH;
								else if (unit.contains("Yearly"))
									field = Calendar.YEAR;
							}
						} else {
							field = Integer.parseInt(pats[1]);
						}
						if (pats[2].startsWith("S_")) {
							// code added by Anwar on 03/02/2016
							// ex $CHANGEDATE_ADD$5$S_dateAddedValue
							if (null != session_information
									&& session_information
											.containsKey(pats[2].substring(2))
									&& Util.isValidObject(session_information
											.get(pats[2].substring(2)))) {
								int amount = Integer.parseInt((String) session_information
										.get(pats[2].substring(2)));
								newDate.add(field, amount);
							} else {
								return null;
							}

						} else {
							int amount = Integer.parseInt(pats[2]);
							newDate.add(field, amount);
						}

					}
				}
			}
			value = newDate.getTime();
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$INTARRAY")) {
			String arrayString = param.getAttributeValue().substring(10,
					param.getAttributeValue().length() - 1);
			String[] intStringArray = arrayString.split(",");
			Object[] objectArray = new Object[intStringArray.length];
			for (int count = 0; count < intStringArray.length; count++) {

				int intvalue = Integer.parseInt(intStringArray[count]);
				objectArray[count] = new Integer(intvalue);
			}
			value = objectArray;
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$STRINGARRAY")) {
			String arrayString = param.getAttributeValue().substring(10,
					param.getAttributeValue().length() - 1);
			String[] intStringArray = arrayString.split(",");
			Object[] objectArray = new Object[intStringArray.length];
			for (int count = 0; count < intStringArray.length; count++) {

				objectArray[count] = intStringArray[count];
			}
			value = objectArray;
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$CONCAT_")) {

			String paramValue = param.getAttributeValue().substring(8);
			StringBuilder builder = new StringBuilder();
			String[] concatenatedParams = paramValue.split(";");

			for (String concatParam : concatenatedParams) {
				ActivitiMediationParameter comsMediationParameter = new ActivitiMediationParameter();
				comsMediationParameter.setAttributeValue(concatParam);
				value = getDynamicparamValue(session_information, comsMediationParameter);
				builder.append(value);
			}

			value = builder.toString();
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().equals("NULL")) {
			value = null;
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$MULTI_")) {
			// $MULTI_$S_SessionVar-$O_orderInfo-1400
			String paramValue = param.getAttributeValue().substring(7);
			String[] numberArray = paramValue.split("-");
			Double result = 1d;
			for (String number : numberArray) {
				if (number.startsWith("$S_")) {
					number = number.substring(3);
					if (session_information.containsKey(number)
							&& Util.isValidObject(session_information.get(number))) {
						result = Double.parseDouble(
								(String) session_information.get(number)) * result;
					}
				} else {
					result = Double.parseDouble(number) * result;
				}
			}

			value = "" + result.longValue();
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$SC_")
				&& param.getWorkflowContext() != null) {
			value = JsonPath.using(conf)
					.parse(JsonUtil.objectToJson(param.getWorkflowContext()))
					.read(param.getAttributeValue().substring(4));
		} else if (param.getAttributeValue() != null
				&& param.getAttributeValue().startsWith("$OC_")
				&& param.getContextOrderInfo() != null) {
			value = JsonPath.using(conf)
					.parse(JsonUtil.objectToJson(param.getContextOrderInfo()))
					.read(param.getAttributeValue().substring(4));
		} else {
			value = param.getAttributeValue();
		}
		return value;
	}

	public static HashMap<String, ActivitiMediationTemplate> getMediationTemplateAsMap(
			List<ActivitiMediationTemplate> allMediationTemplates) {

		HashMap<String, ActivitiMediationTemplate> mediationTemplateMap = new HashMap<String, ActivitiMediationTemplate>();
		for (ActivitiMediationTemplate activitiMediationTemplate : allMediationTemplates) {
			String key = activitiMediationTemplate.getTemplateId();
			mediationTemplateMap.put(key, activitiMediationTemplate);
		}
		return mediationTemplateMap;
	}

	public static List<Long> getDtoIds(BespokeProject project, String dtoType,
			String[] businessTypes) {
		List<Long> dtos = new ArrayList<Long>();
		List<IEntityProjectDTO> projectDtos = project.getProjectDtos();
		for (IEntityProjectDTO dto : projectDtos) {
			for (String businessType : businessTypes) {
				if (dto.getDtoType().endsWith(dtoType)
						&& dto.getBusinessType().getType().equals(businessType)) {
					dtos.add(dto.getId());

				}
			}

		}
		return dtos;
	}

	public static List<IEntityProjectDTO> getDtos(BespokeProject project, String dtoType,
			String[] businessTypes) {
		List<IEntityProjectDTO> dtos = new ArrayList<IEntityProjectDTO>();
		List<IEntityProjectDTO> projectDtos = project.getProjectDtos();
		for (IEntityProjectDTO dto : projectDtos) {
			for (String businessType : businessTypes) {
				if (dto.getDtoType().endsWith(dtoType)
						&& dto.getBusinessType().getType().equals(businessType)) {
					dtos.add(dto);

				}
			}

		}
		return dtos;
	}
	
	
	public static <T> List<T> getDtosInOriginalType(Class<T> dtoClass, BespokeProject project) {

		List<T> dtoList = new ArrayList<T>();
		List<IEntityProjectDTO> projectDtos = project.getProjectDtos();
		for (IEntityProjectDTO dto : projectDtos) {

			if (dto.getDtoType().endsWith("." + dtoClass.getSimpleName())) {
				T originalDto = (T) EntityToDataModelTransformer.transformProjectDTO(dto);
				dtoList.add(originalDto);

			}
		}

		return dtoList;
	}

	/**
	 * This method used to get the DTOs by their type.
	 * 
	 * @param project
	 * @param dtoType
	 * @return
	 */
	public static List<Long> getDtosByType(BespokeProject project, String dtoType) {
		List<IEntityProjectDTO> projectDtos = project.getProjectDtos();
		List<Long> dtos = new ArrayList<Long>();

		for (IEntityProjectDTO dto : projectDtos) {
			if (dto.getDtoType().endsWith(dtoType)) {
				dtos.add(dto.getId());
			}
		}
		return dtos;
	}

	public static boolean checkDtoAttributeExist(long dtoID, String attributeName) {
		boolean attrExist = false;

		return attrExist;
	}

	// start $NUM_ to extract number from value
	// start VAL_ for static string
	// start with $S_ for value from session
	// start with $CONCAT_ to concat many values
	// start with json path to extract value from json
	public static Object getCorrespondingAttributeValue(String attributeValue,
			String projectDTOJsonValue, Map<String, Object> session_information) {
		Object value = null;
		String mappedvalue = null;

		if (!isValidObject(attributeValue))
			return null;

		int start = attributeValue.indexOf("$");
		int end = attributeValue.indexOf("_");

		String startWith = null;
		if (start > -1 && end > -1 && end > start)
			startWith = (String) attributeValue.subSequence(start, end);

		if (attributeValue.contains("$M_")) {
			String[] sides = attributeValue.split(Pattern.quote("$M_"));
			attributeValue = sides[0];
			mappedvalue = sides[1];
		}

		if (attributeValue.startsWith("VAL_")) {
			value = attributeValue.substring(4);
		} else if (attributeValue.startsWith("$SPACE_")) {
			value = attributeValue.replace("$SPACE_", " ");
		} else if (attributeValue != null && attributeValue.startsWith("$S_")) {
			Object var = session_information.get(attributeValue.substring(3));
			value = (var == null) ? null : var.toString();
		} else if (attributeValue != null && attributeValue.startsWith("$NUM_")) {
			value = attributeValue.replace("$NUM_", "");
			String result = (String) getCorrespondingAttributeValue((String) value,
					projectDTOJsonValue, session_information);
			value = extractNumber(result);
		} else if (attributeValue != null && attributeValue.startsWith("$INT_")) {
			value = attributeValue.replace("$INT_", "");
			String result = (String) getCorrespondingAttributeValue((String) value,
					projectDTOJsonValue, session_information);
				value = Integer.valueOf(result);
		} else if (attributeValue != null && attributeValue.startsWith("$STR_")) {
			value = attributeValue.replace("$STR_", "");
			String result = (String) getCorrespondingAttributeValue((String) value,
					projectDTOJsonValue, session_information);
			value = extractAlpha(result);
		} else if (attributeValue != null && attributeValue.startsWith("$VATABLE_")) {
			value = attributeValue.replace("$VATABLE_", "");
			String result = (String) getCorrespondingAttributeValue((String) value,
					projectDTOJsonValue, session_information);
			value = result;
			if (value != null) {
				Double before = Double.valueOf((String) value);
				Double after = before + (before * 0.05);
				value = df2.format(after);
			}
		} else if (attributeValue != null && attributeValue.startsWith("$DEDUCTPER_")) {
			value = attributeValue.replace("$DEDUCTPER_", "");
			String[] sides = ((String) value).split("_");

			String result = (String) getCorrespondingAttributeValue(sides[1],
					projectDTOJsonValue, session_information);
			value = result;
			if (value != null) {
				Double before = Double.valueOf((String) value);
				Double per = Double.valueOf(sides[0]) / 100;
				Double after = before - (before * per);
				value = df2.format(after);
			}
		} else if (attributeValue != null && attributeValue.startsWith("$CONCAT_")) {
			String paramValue = attributeValue.substring(8);
			StringBuilder builder = new StringBuilder();
			String[] concatenatedParams = paramValue.split(";");

			for (String concatParam : concatenatedParams) {
				value = getCorrespondingAttributeValue(concatParam, projectDTOJsonValue,
						session_information);
				builder.append(value);
			}
			value = builder.toString();
		} else if (attributeValue != null && attributeValue.startsWith("$LONG_")) {
			String paramValue = attributeValue.substring(6);
			value = getCorrespondingAttributeValue(paramValue, projectDTOJsonValue,
					session_information);
			value = getinternalMappedValue(mappedvalue, value);
			if (value != null)
				value = getValidLong(value);

		} else if (attributeValue != null && attributeValue.startsWith("$FLOAT_")) {
			String paramValue = attributeValue.substring(7);
			value = getCorrespondingAttributeValue(paramValue, projectDTOJsonValue,
					session_information);
			if (value != null)
				value = getFloatValue(String.valueOf(value));

		} else if (attributeValue != null && attributeValue.startsWith("$DOU_")) {
			String paramValue = attributeValue.substring(5);
			value = getCorrespondingAttributeValue(paramValue, projectDTOJsonValue,
					session_information);
			if (value != null)
				value = getDoubleValue(String.valueOf(value));

		} else if (attributeValue != null && attributeValue.startsWith("$SHO_")) {
			value = Short.valueOf(attributeValue.substring(5));
		} else if (attributeValue != null && attributeValue.startsWith("$DEC_")) {
			String paramValue = attributeValue.substring(5);
			value = getCorrespondingAttributeValue(paramValue, projectDTOJsonValue,
					session_information);
			if (value != null)
				value = getValidBigDecimal(value);
		} else if (attributeValue != null && attributeValue.startsWith("$BYTE_")) {
			String paramValue = attributeValue.substring(6);
			String[] sides = paramValue.split(Pattern.quote("^"));
			String number = (String) getCorrespondingAttributeValue(sides[0],
					projectDTOJsonValue, session_information);
			String uom = (String) getCorrespondingAttributeValue(sides[1],
					projectDTOJsonValue, session_information);

			value = calculateDataInBytes(number, uom);

		} else if (attributeValue != null && attributeValue.startsWith("$KBYTE_")) {
			String paramValue = attributeValue.substring(7);
			String[] sides = paramValue.split(Pattern.quote("^"));
			String number = (String) getCorrespondingAttributeValue(sides[0],
					projectDTOJsonValue, session_information);
			String uom = (String) getCorrespondingAttributeValue(sides[1],
					projectDTOJsonValue, session_information);

			value = calculateDataInKBytes(number, uom);

		} else if (attributeValue != null && attributeValue.startsWith("$SEC_")) {
			String paramValue = attributeValue.substring(5);
			String[] sides = paramValue.split(Pattern.quote("^"));
			String number = (String) getCorrespondingAttributeValue(sides[0],
					projectDTOJsonValue, session_information);
			String uom = (String) getCorrespondingAttributeValue(sides[1],
					projectDTOJsonValue, session_information);

			if (Util.isValidObject(number)) {
				value = getValueInSec(number, uom);
			}

		} else if (attributeValue != null && attributeValue.startsWith("$HOUR_")) {
			String paramValue = attributeValue.substring(6);
			String[] sides = paramValue.split(Pattern.quote("^"));
			String number = (String) getCorrespondingAttributeValue(sides[0],
					projectDTOJsonValue, session_information);
			String uom = (String) getCorrespondingAttributeValue(sides[1],
					projectDTOJsonValue, session_information);

			if (Util.isValidObject(number)) {
				value = getValueInHour(number, uom);
			}

		} else if (attributeValue != null && attributeValue.startsWith("$ANYVALID_")) {
			boolean mapping = false;
			String paramValue = attributeValue.substring(10);
			if(paramValue.contains("#")) {
				String temp[] = paramValue.split(Pattern.quote("#"));
				mappedvalue = temp[1];
				paramValue = temp[0];
				mapping = true;
			}
			String valid[] = paramValue.split(Pattern.quote("|"));
			String result = "false";
			for (String temp : valid) {
				value = getCorrespondingAttributeValue(temp, projectDTOJsonValue,
						session_information);
				if (isValidObject(value)) {
					result = "true";
					break;
				}
			}
			if(mapping) {
				value = doMapping(result, mappedvalue, projectDTOJsonValue, session_information);
			} else {
				value = result;
			}
		} else if (attributeValue != null && attributeValue.startsWith("$ANYVALIDVAL_")) {
			boolean mapping = false;
			String paramValue = attributeValue.substring(13);
			if(paramValue.contains("#")) {
				String temp[] = paramValue.split(Pattern.quote("#"));
				mappedvalue = temp[1];
				paramValue = temp[0];
				mapping = true;
			}
			String valid[] = paramValue.split(Pattern.quote("|"));
			String result = null;
			for (String temp : valid) {
				value = getCorrespondingAttributeValue(temp, projectDTOJsonValue,
						session_information);
				if (isValidObject(value)) {
					result = value.toString();
					break;
				}
			}
			if(mapping) {
				value = doMapping(result, mappedvalue, projectDTOJsonValue, session_information);
			} else {
				value = result;
			}
		} else if (attributeValue != null && attributeValue.startsWith("$ANYVALIDB_")) {
			String paramValue = attributeValue.substring(11);
			String valid[] = paramValue.split(Pattern.quote("|"));
			String result = "0";
			for (String temp : valid) {
				value = getCorrespondingAttributeValue(temp, projectDTOJsonValue,
						session_information);
				if (isValidObject(value)) {
					result = "1";
					break;
				}
			}
			value = result;
		} else if (attributeValue != null && attributeValue.startsWith("$ANYTRUE_")) {
			String paramValue = attributeValue.substring(9);
			boolean mapping = false;
			if(paramValue.contains("#")) {
				String temp[] = paramValue.split(Pattern.quote("#"));
				mappedvalue = temp[1];
				paramValue = temp[0];
				mapping = true;
			}
			String valid[] = paramValue.split(Pattern.quote("|"));
			String result = "0";
			for (String temp : valid) {
				String bool = (String) getCorrespondingAttributeValue(temp,
						projectDTOJsonValue, session_information);
				logger.info("Boolean Value of(" + temp + ") is: " + bool);
				if (Boolean.valueOf(bool)) {
					result = "1";
					break;
				}
			}
			if(mapping) {
				value = doMapping(result, mappedvalue, projectDTOJsonValue, session_information);
			} else {
				value = result;
			}
		} else if (attributeValue != null && attributeValue.startsWith("$ALLTRUE_")) {
			String paramValue = attributeValue.substring(9);
			boolean mapping = false;
			if(paramValue.contains("#")) {
				String temp[] = paramValue.split(Pattern.quote("#"));
				mappedvalue = temp[1];
				paramValue = temp[0];
				mapping = true;
			}
			String valid[] = paramValue.split(Pattern.quote("|"));
			String result = "1";
			for (String temp : valid) {
				String bool = (String) getCorrespondingAttributeValue(temp,
						projectDTOJsonValue, session_information);
				logger.info("Boolean Value of(" + temp + ") is: " + bool);
				if (!Boolean.valueOf(bool)) {
					result = "0";
					break;
				}
			}
			if(mapping) {
				value = doMapping(result, mappedvalue, projectDTOJsonValue, session_information);
			} else {
				value = result;
			}
		} else if (attributeValue != null && attributeValue.startsWith("$MAP_")) {
			String paramValue = attributeValue.substring(5);
			String[] values = paramValue.split(Pattern.quote(";"));

			Map<String, Object> map = new HashMap<String, Object>();

			for (String val : values) {
				String[] sides = val.split(Pattern.quote("="));
				String key = (String) getCorrespondingAttributeValue(sides[0],
						projectDTOJsonValue, session_information);
				Object keyValue = getCorrespondingAttributeValue(sides[1],
						projectDTOJsonValue, session_information);
				map.put(key, keyValue);
			}

			if (!map.isEmpty()) {
				value = map;
			}

		} else if (attributeValue != null && attributeValue.startsWith("$DATE_")) {
			String paramValue = attributeValue.substring(6);
			String date = (String) getCorrespondingAttributeValue(paramValue,
					projectDTOJsonValue, session_information);

			if (isValidObject(date)) {
				logger.log(Level.INFO, "getCorrespondingAttributeValue  DATE = " + date);
				Date dateObject = parseDateString(date, DATE_FORMATS);
				value = dateObject;
			}

		} else if (attributeValue != null && attributeValue.startsWith("$DATEFORMAT_")) {
			String paramValue = attributeValue.substring(13);

			String[] sides = paramValue.split(Pattern.quote("^"));
			String format = sides[0];
			paramValue = sides[1];

			Date date = (Date) getCorrespondingAttributeValue(paramValue,
					projectDTOJsonValue, session_information);

			if (isValidObject(date)) {
				String result = formatDateToString(date, format, null);
				value = result;
			}

		}else if (attributeValue != null && attributeValue.startsWith("$FORMATDATE_")) {
			String paramValue = attributeValue.substring(12);
			if (paramValue != null) {
				String[] pats = paramValue.split("\\$");
				ActivitiLoggingUtil.logMessage(Level.DEBUG,	"OLD DATE FORMATE = " + pats[0]);
				DateFormat df1 = new SimpleDateFormat(pats[0]);
				String date = (String) getCorrespondingAttributeValue(pats[1], projectDTOJsonValue, session_information);
				if (null != date) {
					ActivitiLoggingUtil.logMessage(Level.DEBUG,	"NEW DATE FORMATE = " + pats[2]);
					ActivitiLoggingUtil.logMessage(Level.DEBUG, "DATE VALUE = " + date);
					try {
						value = df1.parse((String) date);
						DateFormat df2 = new SimpleDateFormat(pats[2]);
						value = df2.format(value);
					} catch (ParseException e) {
						logger.error(e.getMessage(), e);
						e.printStackTrace();
					}
				}
			}
		} else if (attributeValue != null && attributeValue.startsWith("$NOW_")) {
			String paramValue = attributeValue.substring(5);

			Date date = Calendar.getInstance().getTime();

			if (isValidObject(paramValue)) {
				String result = formatDateToString(date, paramValue, null);
				value = result;
			} else {
				value = date;
			}

		} else if (attributeValue != null && attributeValue.startsWith("$BOOL_")) {
			String paramValue = attributeValue.substring(6);

			String bool = (String) getCorrespondingAttributeValue(paramValue,
					projectDTOJsonValue, session_information);

			if (isValidObject(bool)) {
				value = Boolean.valueOf(bool);
			}

		}  else if (attributeValue != null && attributeValue.startsWith("$CAMEL_")) {
			String paramValue = attributeValue.substring(7);
			
			Object text = (String) getCorrespondingAttributeValue(paramValue, projectDTOJsonValue, session_information);
			value = text;
			if (isValidObject(text) && text instanceof String) {
				String temp = (String) text;
				if(!temp.startsWith("$")) {
					value = convertToCamelCase(temp);
				}
			}

		} else if (attributeValue != null && attributeValue.startsWith("$JSONPATH_")) {
			String paramValue = attributeValue.substring(10);
			logger.log(Level.INFO, "JSONPATH_paramValue  => " + paramValue);
			logger.log(Level.INFO, "JSONPATH_OriginalJson  => " + projectDTOJsonValue);
			Object obj = null;
			try {
				obj = JsonPath.read(projectDTOJsonValue, paramValue);
				if (obj instanceof JSONArray) {
					JSONArray arr = (JSONArray) obj;
					if (arr.size() == 1) {
						return String.valueOf(arr.get(0));
					}
				}
				return JsonUtil.objectToJson(obj);

			} catch (Exception e) {
				logger.log(Level.INFO,
						"JSONPATH_  => " + ExceptionUtils.getStackTrace(e));
			}
			return obj;
		} else if (attributeValue != null && attributeValue.startsWith("$JSONARRAY_")) {
			String paramValue = attributeValue.substring(11);
			return readJsonPath(projectDTOJsonValue, paramValue);
		} else {
			String method = extractAttributeMethod(attributeValue);
			if (isValidObject(method)) {
				logger.log(Level.INFO, "Util template method => " + method);
				attributeValue = attributeValue.replace(method, "");
				if (method.startsWith("$REPLACE")) {
					String temp = (String) getCorrespondingAttributeValue(attributeValue,
							projectDTOJsonValue, session_information);

					logger.log(Level.INFO,
							"Util template value to be updated => " + temp);

					List<String> params = extractMethodParams(method);
					if (isValidateCollection(params) && params.size() > 1
							&& isValidObject(temp)) {
						String param1 = params.get(0).replace("\\", "");
						String param2 = params.get(1).replace("\\", "");
						value = temp.replace(param1, param2);
						logger.log(Level.INFO,
								"Util template value after updated => " + value);
					}
				} else if (method.startsWith("$LIST")) {
					String temp = (String) getCorrespondingAttributeValue(attributeValue,
							projectDTOJsonValue, session_information);
					logger.log(Level.INFO, "Util template value to be list => " + temp);
					List<String> params = extractMethodParams(method);
					if (isValidateCollection(params) && params.size() > 0
							&& isValidObject(temp)) {
						logger.log(Level.INFO,
								"Util template value to split with => " + params.get(0));
						String[] valueAsArray = temp.split(params.get(0));
						value = Arrays.asList(valueAsArray);
					}
				} else if (method.startsWith("$MATH")) {
					String temp = (String) getCorrespondingAttributeValue(attributeValue, projectDTOJsonValue, session_information);
					List<String> params = extractMethodParams(method);
					if (isValidateCollection(params) && params.size() == 2 && isValidObject(temp)) {
						logger.log(Level.INFO, "Complex method = " + method);
						String operation = params.get(0);
						String val = params.get(1);
						
						logger.log(Level.INFO, "Complex method = " + method + " PARAM 1 = " + operation + " PARAM 2 = " + val);

						if (val.startsWith("$")) {
							val = (String) getCorrespondingAttributeValue(val.replace("$", ""), projectDTOJsonValue, session_information);
						}

						value = calculate(operation, val, temp);
					}
				} else if (method.startsWith("$INDEX")) {
					List temp = (List) getCorrespondingAttributeValue(attributeValue, projectDTOJsonValue,
							session_information);
					logger.log(Level.INFO, "list value to get index from => " + temp);
					List<String> params = extractMethodParams(method);
					if (isValidateCollection(params) && params.size() > 0 && isValidObject(temp)) {
						logger.log(Level.INFO, "index to be selected from list => " + params.get(0));
						int index = Integer.valueOf(params.get(0));
						if ((index + 1) <= temp.size()) {
							value = temp.get(index);
						} else {
							value = null;
						}
					}
					if (isValidateCollection(params) && params.size() > 1) {
						value = doMapping(value, params.get(1), projectDTOJsonValue, session_information);
					}
				} else if (method.startsWith("$XOR")) {
					String temp = (String) getCorrespondingAttributeValue(attributeValue, projectDTOJsonValue, session_information);
					List<String> params = extractMethodParams(method);
					if (isValidateCollection(params) && params.size() >= 1 && isValidObject(temp)) {
						logger.log(Level.INFO, "Complex method = " + method);
						String secondSide = params.get(0);
						

						if (secondSide.startsWith("$")) {
							secondSide = (String) getCorrespondingAttributeValue(secondSide.replace("$", ""), projectDTOJsonValue, session_information);
						}
						
						value = Boolean.valueOf(temp) ^ Boolean.valueOf(secondSide);

						if (isValidateCollection(params) && params.size() > 1) {
							value = doMapping(String.valueOf(value), params.get(1), projectDTOJsonValue, session_information);
						}
					}
				}
			} else {

				if (attributeValue.contains("#")) {
					String[] arrSplitter = attributeValue.split("#",2);
					attributeValue = arrSplitter[0];
					mappedvalue = arrSplitter[1];
				}
				Object object = null;
				if (attributeValue.contains("+")) {
					String[] splitterArr = attributeValue.split("[+]");
					boolean flag = true;
					for (String s : splitterArr) {
						object = readJsonPath(projectDTOJsonValue, s);
						flag = flag && (Boolean.valueOf(String.valueOf(object)));
					}
					object = flag;
				} else {
					object = readJsonPath(projectDTOJsonValue, attributeValue);
				}

				value = arrayToComaString(object);

				value = getinternalMappedValue(mappedvalue, value);

				if (isValidObject(value) && (value instanceof String)
						&& ((String) value).startsWith("$EVAL_")) {
					String temp = (String) value;
					temp = temp.substring(6);

					value = getCorrespondingAttributeValue(temp, projectDTOJsonValue,
							session_information);
				}
			}
		}

		if (value != null && value instanceof String
				&& !"$SPACE".equalsIgnoreCase(startWith))
			value = ((String) value).trim();

		if (value != null && value instanceof String)
			value =((String) value).replaceAll("$COMA$", ",");

		return value;
	}	
	private static Object doMapping(Object value, String mappedvalue, String projectDTOJsonValue, Map<String, Object> session_information) {
		value = getinternalMappedValue(mappedvalue, value);

		if (isValidObject(value) && (value instanceof String) && ((String) value).startsWith("$EVAL_")) {
			String temp = (String) value;
			temp = temp.substring(6);

			value = getCorrespondingAttributeValue(temp, projectDTOJsonValue, session_information);
		}

		return value;
	}

	public static String calculate(String op, String val, String actual) {
		float temp = 0;
		switch (op) {
		case "+":
			temp = Float.valueOf(actual);
			temp = temp + Float.parseFloat(val);
			break;
		case "-":
			temp = Float.valueOf(actual);
			temp = temp - Float.parseFloat(val);
			break;
		case "*":
			temp = Float.valueOf(actual);
			temp = temp * Float.parseFloat(val);
			break;

		default:
			break;
		}
		return String.valueOf(temp);
	}

	private static Object getinternalMappedValue(String mappedvalue, Object value) {
		if (Util.isValidObject(mappedvalue)) {
			String temp = (String) value;
			value = getMappedValue((String) value, mappedvalue);
			if (!Util.isValidObject(value)) {
				logger.error("wrong Mapping for value [" + temp
						+ "] and mapping options [" + mappedvalue + "]");
			}
		}
		return value;
	}

	public static String arrayToComaString(Object object) {
		String value = null;
		if (Util.isValidObject(object)) {
			value = String.valueOf(object);
			if (value.startsWith("[") && value.endsWith("]")) {
				String[] arr = JsonUtil.jsonToObject(value, String[].class);
				String z = "";
				for (int i = 0; i < arr.length; i++) {
					String val = arr[i];
					if ("".equals(z)) {
						z = val;
					} else {
						z = z + "," + val;
					}
				}
				value = z;
			}
		}
		return value;
	}

	public static String extractNumber(String value) {
		String result = null;
		if (value != null) {
			result = value.replaceAll("[^-?0-9]+", "");
			result = result.trim();
		}
		return result;
	}

	public static String extractAlpha(String value) {
		String result = null;
		if (value != null) {
			result = value.replaceAll("[^a-zA-Z]+", "");
			result = result.trim();
		}
		return result;
	}

	public static String convertToCamelCase(String sentence) {

		// Extract all words
		String words[] = sentence.split("\\s+");

		// Creating an empty string of type StringBuilder so that modification
		// of string is possible.
		StringBuilder sb = new StringBuilder();

		// Iterating through words
		for (String word : words) {
			// Extracting first char
			char firstChar = word.charAt(0);
			
			sb.append(Character.toUpperCase(firstChar)).append(word.substring(1).toLowerCase()).append(" ");

		}

		// Converting StringBuilder to String. trim() is needed to trim last
		// space appended.
		String result = sb.toString().trim();
		return result;
	}

	public static String getMappedValue(String attributeValue, String mappedValues) {
		String realValue = null;
//		if (!Util.isValidObject(attributeValue)) {
//			return realValue;
//		}
		// sample for multi mapping 
		// promoCard#false|$EVAL_VAL_DISCOUNT_FRAMWORK,true|$EVAL_cardType#THUKHER|THUKHAR,ESAAD|ESAAD
		String tail = "";
		if(mappedValues.contains("#")) {
			String[] split = mappedValues.split("#",2);
			mappedValues = split[0];
			tail = "#"+split[1];
		}
		String values[] = mappedValues.split(",");
		String arrSplitter[] = null;
		int index = 0;
		for (String mappedValue : values) {
			index++;
			arrSplitter = mappedValue.split("\\|");
			if ((attributeValue == null && "null".equalsIgnoreCase(arrSplitter[0]))
					|| (attributeValue != null && attributeValue.equalsIgnoreCase(arrSplitter[0]))
					|| "ELSE".equalsIgnoreCase(arrSplitter[0])) {
				if (arrSplitter.length > 1) {
					realValue = arrSplitter[1];
				} else {
					return null;
				}
				break;
			}
		}
		if (realValue == null)
			realValue = attributeValue;
		if(index == values.length&&isValidObject(tail)) {
			realValue+=tail;
		}
		return realValue;
	}
	
	public static String getMappedValue(String attributeValue, String mappedValues, String projectDTOJsonValue, Map<String, Object> session) {
		String realValue = null;
		if (!Util.isValidObject(attributeValue)) {
			return realValue;
		}

		String values[] = mappedValues.split(",");
		String arrSplitter[] = null;
		for (String mappedValue : values) {
			arrSplitter = mappedValue.split("\\|");
			
			if (attributeValue.equalsIgnoreCase(arrSplitter[0]) || "ELSE".equalsIgnoreCase(arrSplitter[0])) {
				if (arrSplitter.length > 1) {
					String value = arrSplitter[1];
					if (isValidObject(value) && (value instanceof String) && ((String) value).startsWith("$EVAL_")) {
						String temp = (String) value;
						temp = temp.replace("$EVAL_", "");

						realValue = (String)getCorrespondingAttributeValue(temp, projectDTOJsonValue, session);
					}else if(isValidObject(value) && (value instanceof String) && ((String) value).startsWith("$SKIP")){
						return null;
					}else{
						realValue = arrSplitter[1];
					}
					
				} else {
					return null;
				}
				break;
			}
		}
		if(realValue == null)
			realValue = attributeValue;
		return realValue;
	}

	public static boolean validateIsMandatory(String attributeValue) {
		boolean isMandatory = false;
		if (attributeValue.contains(":")) {
			String checkMandatory[] = attributeValue.split(":");
			if (checkMandatory[1].equalsIgnoreCase("M")) {
				isMandatory = true;
			}
		}
		return isMandatory;
	}
	
	public static String evalAttribute(String attributeValue, String projectDTOJsonValue, String paramValues, Map<String,Object> contents) {
		return evalAttribute(attributeValue, projectDTOJsonValue, paramValues, contents, false);
	}
	
	public static String evalAttribute(String attributeValue, String projectDTOJsonValue, String paramValues, Map<String,Object> contents,boolean isIfElseMapping) {
		String value = null;
		String mappedvalue = null;
		
		if(attributeValue.startsWith(JSON_CONFIG_TOKEN)) {
			value = Objects.toString(contents.get(attributeValue.replaceFirst(JSON_CONFIG_TOKEN_REGEXP, "")));
			return evalAttribute(value, projectDTOJsonValue, paramValues,contents);			
		} else if (attributeValue.startsWith(JSON_PATH_TOKEN)) {
			value = attributeValue.replaceFirst(JSON_PATH_TOKEN_REGEXP, ""); 
			return evalAttribute(value, projectDTOJsonValue, paramValues, contents);
		} else if (attributeValue.startsWith("VAL_")) {
			value = attributeValue.replaceFirst("VAL_", "");
		} else if (attributeValue.startsWith("PARAM_")) {
			String paramOrder = attributeValue.split("_")[1];
			value = paramValues.split("\\|")[Integer.parseInt(paramOrder)];
		} else if(isIfElseMapping){
			value=attributeValue;
		} else {
			if (attributeValue.contains("#")) {
				String[] arrSplitter = attributeValue.split("#");
				attributeValue = arrSplitter[0];
				mappedvalue = arrSplitter[1];
			}
			
			Object object = evalJsonPath(projectDTOJsonValue, attributeValue);
			logger.info("key:["+attributeValue+"] object [" + Objects.toString(object) + "]");
			if (Util.isValidObject(object) && attributeValue.indexOf("insur")==-1) {
				value = String.valueOf(object);
				if (value.startsWith("[") && value.endsWith("]")) {
					String[] arr = JsonUtil.jsonToObject(value, String[].class);
					String z = "";
					for (int i = 0; i < arr.length; i++) {
						String val = arr[i];
						if ("".equals(z)) {
							z = val;
						} else {
							z = z + "," + val;
						}
					}
					value = z;
				}
			}

			if (Util.isValidObject(mappedvalue) /*&& Util.isValidObject(value)*/) {
				value = evalIfElse(value, mappedvalue, projectDTOJsonValue, paramValues,contents);
				if (!Util.isValidObject(value)) {
					logger.error("wrong Mapping for value [" + value + "] and mapping options [" + mappedvalue + "]");
				}
			}
		}
		
		return value;
	}
	
	public static Object evalJsonPath(String jsonStr, String path) {
		Object object = null;
		try {
			object = JsonPath.read(jsonStr, path);
		} catch (Exception e) {
			logger.debug("path " + path + " was not avialble in provided JSON Igonring the value");
		}
		return object;
	}
	
	
	public static String evalIfElse(String attributeValue, String mappedValues, String projectDTOJsonValue,
			String params,Map<String,Object> contents) {
		String realValue = null;

		String values[] = mappedValues.split(",");
		String arrSplitter[] = null;
		boolean found = false;
		for (String mappedValue : values) {
			arrSplitter = mappedValue.split("\\|");
			
			if(arrSplitter[0].contains("\\")) {
				if(String.format("\\%s\\",arrSplitter[0]).contains(String.format("\\%s\\",attributeValue))) {
					found = true;
				}
			} else if ((StringUtils.isBlank(attributeValue) || ("null".equalsIgnoreCase(attributeValue)) && "$BLANK".equalsIgnoreCase(arrSplitter[0])) ||  attributeValue.equalsIgnoreCase(arrSplitter[0]) || "ELSE".equalsIgnoreCase(arrSplitter[0])) { //scalar value exists only
				found = true;
			}		
			
			if(found) {
				realValue = evalAttribute(arrSplitter[1], projectDTOJsonValue, params, contents,true);
				break;
			} 
		}
		return realValue;
	}
	
	public static Float getFloatValue(String input) {
		Float output = null;
		if (isValidObject(input))
			output = new Float(input);
		return output;
	}
	
	public static Double getDoubleValue(String input) {
		Double output = null;
		if (isValidObject(input))
			output = new Double(input);
		return output;
	}

	public static BigInteger getBigIntegerValue(String input) {
		BigInteger output = null;
		if (isValidObject(input))
			output = new BigInteger(input);
		return output;
	}

	public static Long getLongValue(String input) {
		Long output = null;
		if (isValidObject(input))
			output = Long.valueOf(input);
		return output;
	}

	public static Short getShortValue(String input) {
		Short output = null;
		if (isValidObject(input))
			output = Short.valueOf(input);
		return output;
	}

	public static boolean isTestingMode(DelegateExecution execution) {
		return "TRUE"
				.equalsIgnoreCase((String) execution.getVariable("skip#RealNetwork"));
	}

	public static boolean isTestingChannel(DelegateExecution execution) {
		return "TRUE".equalsIgnoreCase(
				(String) execution.getVariable(Constants.OPERATION_FLAG_VAR));
	}

	public static XMLGregorianCalendar DateToXmlDate(Date value)
			throws DatatypeConfigurationException {
		GregorianCalendar c = new GregorianCalendar();
		c.setTime(value);
		XMLGregorianCalendar date = DatatypeFactory.newInstance()
				.newXMLGregorianCalendar(c);
		date.setTimezone(DatatypeConstants.FIELD_UNDEFINED);
		return date;
	}

	public static List<String> getCommaSeparatedAsList(String str) {

		List<String> list = new ArrayList<String>();
		if (str == null || str.length() < 1) {
			return list;
		}

		if (!str.contains(",")) {
			list.add(str);
			return list;
		}

		String temp[] = str.split(",");
		if (temp != null && temp.length > 0) {
			for (String item : temp) {
				list.add(item);
			}
		}

		return list;
	}

	public static Object fromJson(String json, Class clas) {
		Object res = gson.fromJson(json, clas);
		return res;
	}

	public static <T> T xmlToObj(String xml, Class<T> clazz) throws Exception {
		JAXBContext jaxbContext = JAXBContext.newInstance(clazz);
		Unmarshaller jaxbUnmarshaller = jaxbContext.createUnmarshaller();
		StringReader reader = new StringReader(xml);
		T customer = (T) jaxbUnmarshaller.unmarshal(reader);
		return customer;
	}

	public static String objToXml(Object obj) throws IOException {
		String xmlString = "";
		try {
			xmlString = marshal(obj);
		} catch (Exception e) {
			return javaObjectToXml(obj);
		}
		return xmlString;
	}
	
	public static List<String> getSICPRSs(String sicCode,int connectionTimeout,int readTimeout) throws Exception {
		List<String> prss = new ArrayList<>();
		String url = Config.settings.get("ecm.get.prs.for.sic.service.url")+sicCode;
		String reply = (String) JerseyClientUtil.process(url, null, "GET", null,connectionTimeout,readTimeout, false);
		JsonObject convertedObject = new Gson().fromJson(reply, JsonObject.class);
		if(null!=convertedObject.get("itemList")&&convertedObject.get("itemList").isJsonArray()){
			JsonArray  jsonArray= convertedObject.get("itemList").getAsJsonArray();
			for(int i =0 ; i< jsonArray.size();i++)
			{
				JsonObject element = jsonArray.get(i).getAsJsonObject();
				prss.add(element.get("itemCode").getAsString());
			}
		}
		if(prss.size()==0)
			throw new Exception("PRS not found ");
		return prss;
	}
	
	public static String removeNonAscii(String value) {
		if (value != null)
			value = value.replaceAll("[^\\p{ASCII}]", "");
		return value;
	}
	
	public static String replaceIndexAndSuffix(String value,int index, String suffix) {
		if(isValidObject(value)) {
			value = value.replace("$INDX", index+"").replace("$SUFFIX", suffix);
		}
		return value;
	}
	
	public static void invokeSetter(Object obj, String propertyName, Object variableValue)
    {
        PropertyDescriptor pd;
        try {
            pd = new PropertyDescriptor(propertyName, obj.getClass());
            Method setter = pd.getWriteMethod();
            try {
                setter.invoke(obj,variableValue);
            } catch (IllegalAccessException | IllegalArgumentException | InvocationTargetException e) {
                logger.error(e);
            }
        } catch (IntrospectionException e) {
        	logger.error(e);
        }
 
    }
	
    public static void updateStringProperty(Object obj, String fieldName, String newValue) throws Exception {
        if (obj == null || fieldName == null || newValue == null) {
            throw new IllegalArgumentException("Object, field name, and new value must not be null.");
        }
        // Get the Class object of the provided object
        Class<?> clazz = obj.getClass();
        // Retrieve the field by name
        Field field = clazz.getDeclaredField(fieldName);
        // Ensure the field is of type String
        if (field.getType() != String.class) {
            throw new IllegalArgumentException("Field '" + fieldName + "' is not of type String.");
        }
        // Make the field accessible if it is private or protected
        field.setAccessible(true);
        // Update the field value
        field.set(obj, newValue);
    }
}
