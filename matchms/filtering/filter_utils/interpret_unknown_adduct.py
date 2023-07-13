"""Calculates the multiplier and correction mass for an adduct"""

import logging
import re
from typing import List, Optional, Tuple
from matchms.constants import ELECTRON_MASS


try:  # rdkit is not included in pip package
    from rdkit import Chem
except ImportError:
    _has_rdkit = False
    from collections import UserString

    class ChemMock(UserString):
        def __call__(self, *args, **kwargs):
            return self

        def __getattr__(self, key):
            return self

    Chem = AllChem = ChemMock("")
else:
    _has_rdkit = True
rdkit_missing_message = "Conda package 'rdkit' is required for this functionality."


logger = logging.getLogger("matchms")


def get_multiplier_and_mass_from_adduct(adduct: str) -> Tuple[Optional[float], Optional[float]]:
    """Get multiplier for charge and the actual mass of an adduct.

    Args:
        adduct (str): String description of the adduct.

    Returns:
        Tuple[Optional[float], Optional[float]]: Multiplier and mass of this adduct.
    """
    charge = get_charge_of_adduct(adduct)
    if charge is None:
        return None, None

    parent_mass, ions = get_ions_from_adduct(adduct)

    if parent_mass is None or ions is None:
        return None, None

    mass_of_ions = get_mass_of_ion(ions)
    if mass_of_ions is None:
        return None, None
    added_mass = mass_of_ions - ELECTRON_MASS * charge

    multiplier = 1/abs(charge)*parent_mass
    correction_mass = added_mass/(abs(charge))
    return multiplier, correction_mass


def get_ions_from_adduct(adduct: str) -> Tuple[float, List[str]]:
    """Returns a list of ions from an adduct.

    e.g. '[M+H-H2O]2+' -> ["M", "+H", "-H2O"]
    """

    # Get adduct from brackets
    if "[" in adduct:
        ions_part = re.findall((r"\[(.*)\]"), adduct)
        if len(ions_part) != 1:
            logger.warning("Expected to find brackets [] once, not the case in %s",
                           adduct)
            return None, None
        adduct = ions_part[0]
    # Finds the pattern M or 2M in adduct it makes sure it is in between
    parent_mass = re.findall(r'(?:^|[+-])([0-9]?M)(?:$|[+-])', adduct)
    if len(parent_mass) != 1:
        logger.warning("The parent mass (e.g. 2M or M) was found %s times in %s",
                       len(parent_mass), adduct)
    parent_mass = parent_mass[0]
    if parent_mass == "M":
        parent_mass = 1
    else:
        parent_mass = int(parent_mass[0])

    ions_split = re.findall(r'([+-][0-9a-zA-Z]+)', adduct)
    ions_split = replace_abbreviations(ions_split)
    return parent_mass, ions_split


def split_ion(ion: str) -> Tuple[str, str, str]:
    """Separate an ion description string into sign, number and formula.

    Args:
        ion (str): String representing the ion.

    Returns:
        Tuple[str, str, str]: Components of the ion descirption.
    """
    sign = ion[0]
    ion = ion[1:]
    assert sign in ["+", "-"], "Expected ion to start with + or -"
    match = re.match(r'^([0-9]+)(.*)', ion)
    if match:
        number = match.group(1)
        ion = match.group(2)
    else:
        number = 1
    return sign, number, ion


def replace_abbreviations(ions_split):
    """Derived from https://github.com/pnnl/MSAC"""
    abbrev_to_formula = {'ACN': 'CH3CN', 'DMSO': 'C2H6OS', 'FA': 'CH2O2',
                         'HAc': 'CH3COOH', 'Hac': 'CH3COOH', 'TFA': 'C2HF3O2',
                         'IsoProp': 'CH3CHOHCH3', 'MeOH': 'CH3OH'}
    corrected_ions = []
    for ion in ions_split:
        sign, number, ion = split_ion(ion)
        ion = abbrev_to_formula.get(ion, ion)
        corrected_ions.append(sign + str(number) + ion)
    return corrected_ions


def get_mass_of_ion(ions):
    """Derived from https://github.com/pnnl/MSAC"""
    added_mass = 0
    for ion in ions:
        sign, number, ion = split_ion(ion)
        atom_mass = get_mass_of_formula(ion)
        if atom_mass is None:
            return None

        if sign == "-":
            number = -int(number)
        else:
            number = int(number)
        added_mass += number * atom_mass
    return added_mass


def get_charge_of_adduct(adduct)->Optional[int]:
    charge = re.findall((r"\]([0-9]?[+-])"), adduct)
    if len(charge) != 1:
        logger.warning("Charge was found %s times in adduct %s",
                       len(charge), adduct)
        return None
    charge = charge[0]
    if len(charge) == 1:
        charge_size = "1"
        charge_sign = charge
    elif len(charge) == 2:
        charge_size = charge[0]
        charge_sign = charge[1]
    else:
        logger.warning("Charge is expected of length 1 or 2, but %s was given", charge)
        return None
    return int(charge_sign+charge_size)


def get_mass_of_formula(formula):
    """Calculates the monoisotopic mass of an formula

    e.g. "C" returns 12.011 and "CH2" returns 15.035. This can be used to calculate the mass difference of adducts
    Was adapted from: https://bioinformatics.stackexchange.com/questions/6852/
    """
    if not _has_rdkit:
        raise ImportError(rdkit_missing_message)
    parts = re.findall("[A-Z][a-z]?|[0-9]+", formula)
    mass = 0

    for i, part in enumerate(parts):
        if part.isnumeric():
            continue
        periodic_table = Chem.GetPeriodicTable()
        try:
            atom_mass = periodic_table.GetMostCommonIsotopeMass(part)
        except RuntimeError:
            logger.warning("The atom: %s in the formula %s is not known", part, formula)
            return None
        multiplier = int(parts[i + 1]) if len(parts) > i + 1 and parts[i + 1].isnumeric() else 1
        mass += atom_mass * multiplier
    return mass