"""Platform for sensor integration."""
import logging
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from . import DOMAIN, CONF_HOST, CONF_FORMAT, CONF_NAME, CONF_PARAMS, CONF_PARAMS_STANDARD, CONF_PARAMS_FULL, CONF_LANG, CONF_LANG_EN, CONF_LANG_DE
from datetime import timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from telnetlib import Telnet
import xml.etree.ElementTree as xml
from .hargassner import HargassnerBridge


_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform."""
    host = hass.data[DOMAIN][CONF_HOST]
    format = hass.data[DOMAIN][CONF_FORMAT]
    name = hass.data[DOMAIN][CONF_NAME]
    paramSet = hass.data[DOMAIN][CONF_PARAMS]
    lang = hass.data[DOMAIN][CONF_LANG]
    uniqueId = hass.data[DOMAIN][CONF_LANG]
    bridge = HargassnerBridge(host, uniqueId, msgFormat=format)
    errorLog = bridge.getErrorLog()
    if errorLog != "": _LOGGER.error(errorLog)
    if paramSet == CONF_PARAMS_FULL:
        entities = []
        for p in bridge.data().values(): 
            if p.key()=="Störung": 
                entities.append(HargassnerErrorSensor(bridge, name))
            elif p.key()=="ZK": 
                entities.append(HargassnerStateSensor(bridge, name, lang))
            else:
                entities.append(HargassnerSensor(bridge, name+" "+p.description(), p.key()))
        add_entities(entities)
    else:
        add_entities([
            HargassnerErrorSensor(bridge, name),
            HargassnerStateSensor(bridge, name, lang),
            HargassnerSensor(bridge, name+" boiler temperature", "TK"),
            HargassnerSensor(bridge, name+" smoke gas temperature", "TRG"),
            HargassnerSensor(bridge, name+" output", "Leistung", "mdi:fire"),
            HargassnerSensor(bridge, name+" outside temperature", "Taus"),
            HargassnerSensor(bridge, name+" buffer temperature 0", "TB1", "mdi:thermometer-lines"),
            HargassnerSensor(bridge, name+" buffer temperature 1", "TPo", "mdi:thermometer-lines"),
            HargassnerSensor(bridge, name+" buffer temperature 2", "TPm", "mdi:thermometer-lines"),
            HargassnerSensor(bridge, name+" buffer temperature 3", "TPu", "mdi:thermometer-lines"),
            HargassnerSensor(bridge, name+" return temperature", "TRL", "mdi:coolant-temperature"),
            HargassnerSensor(bridge, name+" buffer level", "Puff Füllgrad", "mdi:gauge"),
            HargassnerSensor(bridge, name+" pellet stock", "Lagerstand", "mdi:silo"),
            HargassnerSensor(bridge, name+" pellet consumption", "Verbrauchszähler", "mdi:basket-unfill"),
            HargassnerSensor(bridge, name+" flow temperature", "TVL_1", "mdi:coolant-temperature"),
            HargassnerEnergySensor(bridge, name)
    ])


class HargassnerSensor(SensorEntity):
    """Representation of a Sensor."""

    def __init__(self, bridge, description, paramName, icon=None):
        """Initialize the sensor."""
        self._value = None
        self._bridge = bridge
        self._description = description
        self._paramName = paramName
        self._icon = icon
        self._unique_id = bridge.getUniqueId()
        self._unit = bridge.getUnit(paramName)
        sc = bridge.getStateClass(paramName)
        if sc=="measurement": self._stateClass = SensorStateClass.MEASUREMENT
        elif sc=="total": self._stateClass = SensorStateClass.TOTAL
        elif sc=="total_increasing": self._stateClass = SensorStateClass.TOTAL_INCREASING
        if self._unit=="°C": self._deviceClass = SensorDeviceClass.TEMPERATURE
        else: self._deviceClass = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._description

    @property
    def device_class(self):
        """Return the state of the sensor."""
        return self._deviceClass

    @property
    def state_class(self):
        """Return the state of the sensor."""
        return self._stateClass

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._value

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        """Return an icon for the sensor in the GUI."""
        return self._icon

    def update(self):
        """Fetch new state data for the sensor.
        This is the only method that should fetch new data for Home Assistant.
        """
        self._value = self._bridge.getValue(self._paramName)

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        return self._unique_id + self._paramName

class HargassnerEnergySensor(HargassnerSensor):

    def __init__(self, bridge, deviceName):
        super().__init__(bridge, deviceName+" energy consumption", "Verbrauchszähler", "mdi:radiator")
        self._deviceClass = SensorDeviceClass.ENERGY
        self._unit = "kWh"

    def update(self):
        self._value = 4.8 * float(self._bridge.getValue(self._paramName))

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        return self._unique_id + self._paramName + "-E"


class HargassnerErrorSensor(HargassnerSensor):

    ERRORS = {
        "5" : "Aschelade entleeren", 
        "6" : "Aschelade zu voll", 
       "29" : "Verbrennungsstörung", 
       "30" : "Batterie leer", 
       "31" : "Blockade Einschubmotor", 
       "32" : "Füllzeit überschritten", 
       "70" : "Pelletslagerstand niedrig", 
       "89" : "Schieberost schwergängig", 
       "93" : "Aschelade offen", 
      "227" : "Lagerraumschalter aus", 
      "228" : "Pelletsbehälter fast leer", 
      "229" : "Füllstandsmelder kontrollieren", 
      "371" : "Brennraum prüfen"
    }

    def __init__(self, bridge, deviceName):
        super().__init__(bridge, deviceName+" operation", "Störung", "mdi:alert")

    def update(self):
        rawState = self._bridge.getValue(self._paramName)
        if rawState==None: self._value = "Unknown"
        elif rawState=="False":
            self._value = "OK"
            self._icon = "mdi:check"
        else:
            errorID = self._bridge.getValue("Störungs Nr")
            errorDescr = self.ERRORS.get(errorID)
            if errorDescr==None:
                self._value = "error " + errorID
            else:
                self._value = errorDescr
            self._icon = "mdi:alert"
        errorLog = self._bridge.getErrorLog()
        if errorLog != "": _LOGGER.error(errorLog)
        infoLog = self._bridge.getInfoLog()
        if infoLog != "": _LOGGER.info(infoLog)


class HargassnerStateSensor(HargassnerSensor):

    UNKNOWN_STATE = "?"
    STATES = {
        "1" : {CONF_LANG_DE:"Aus", CONF_LANG_EN:"Off"},
        "2" : {CONF_LANG_DE:"Startvorbereitung", CONF_LANG_EN:"Preparing start"},
        "3" : {CONF_LANG_DE:"Kessel Start", CONF_LANG_EN:"Boiler start"},
        "4" : {CONF_LANG_DE:"Zündüberwachung", CONF_LANG_EN:"Monitoring ignition"},
        "5" : {CONF_LANG_DE:"Zündung", CONF_LANG_EN:"Ignition"},
        "6" : {CONF_LANG_DE:"Übergang LB", CONF_LANG_EN:"Transition to FF"},
        "7" : {CONF_LANG_DE:"Leistungsbrand", CONF_LANG_EN:"Full firing"},
        "8" : {CONF_LANG_DE:"Gluterhaltung", CONF_LANG_EN:"Ember preservation"},
        "9" : {CONF_LANG_DE:"Warten auf EA", CONF_LANG_EN:"Waiting for AR"},
       "10" : {CONF_LANG_DE:"Entaschung", CONF_LANG_EN:"Ash removal"},
       "12" : {CONF_LANG_DE:"Putzen", CONF_LANG_EN:"Cleaning"},
       UNKNOWN_STATE : {CONF_LANG_DE:"Unbekannt", CONF_LANG_EN:"Unknown"}
    }

    def __init__(self, bridge, deviceName, lang):
        super().__init__(bridge, deviceName+" boiler state", "ZK")
        self._lang = lang

    def update(self):
        rawState = self._bridge.getValue(self._paramName)
        if rawState in self.STATES:
            self._value = self.STATES[rawState][self._lang]
        else: 
            self._value = self.STATES[self.UNKNOWN_STATE][self._lang] + " (" + (str)(rawState) + ")"
        if rawState=="6" or rawState=="7": self._icon = "mdi:fireplace"
        else: self._icon = "mdi:fireplace-off"
