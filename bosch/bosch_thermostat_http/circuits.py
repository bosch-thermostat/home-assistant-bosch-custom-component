"""Circuits module of Bosch thermostat."""
from .const import HC, HEATING_CIRCUITS, DHW_CIRCUITS, MAIN_URI, ID
from .helper import BoschEntities


class Circuits(BoschEntities):
    """Circuits main object containing multiple Circuit objects."""

    def __init__(self, requests, circuit_type):
        """
        Initialize circuits.

        :param dict requests: { GET: get function, SUBMIT: submit function}
        :param str circuit_type: is it HC or DHW
        """
        self._circuit_type = HEATING_CIRCUITS if circuit_type == HC else DHW_CIRCUITS
        super().__init__(requests)

    @property
    def circuits(self):
        """Get circuits."""
        return self.get_items()

    async def initialize(self, database, str_obj, current_date):
        """Initialize HeatingCircuits asynchronously."""
        uri = database[self._circuit_type][MAIN_URI]
        circuits = await self.retrieve_from_module(1, uri)
        for circuit in circuits:
            if "references" in circuit:
                circuit_object = self.create_circuit(
                    circuit, database, str_obj, current_date
                )
                if circuit_object:
                    await circuit_object.initialize()
                    if circuit_object.state:
                        self._items.append(circuit_object)

    def create_circuit(self, circuit, database, str_obj, current_date):
        """Create single circuit of given type."""
        if self._circuit_type == DHW_CIRCUITS:
            from .dhw_circuit import DHWCircuit

            return DHWCircuit(
                self._requests, circuit[ID], database, str_obj, current_date
            )
        if self._circuit_type == HEATING_CIRCUITS:
            from .heating_circuit import HeatingCircuit

            return HeatingCircuit(
                self._requests, circuit[ID], database, str_obj, current_date
            )
        return None
