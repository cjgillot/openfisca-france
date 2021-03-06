# -*- coding: utf-8 -*-

from __future__ import division


import logging

from numpy import datetime64, logical_and as and_, logical_or as or_, logical_xor as xor_, round as round_

from openfisca_core import periods
from openfisca_france.model.base import *  # noqa analysis:ignore


log = logging.getLogger(__name__)


# TODO: 8ti et 8tk (cerfa 2047)
# TODO: CSG, CRDS et prélèvements sociaux sur revenu du patrimione, d'activité et de remplacement
# TODO: finir RPNS (prise en compte des plafonds / cases non codées : codées pour certaines années mais pas pour
# d'autres - car des cases sont réutilisées pour des variables différentes suivant les années)

# zetrf = zeros(taille)
# jeune_veuf = zeros(taille, dtype = bool)
# Reprise du crédit d'impôt en faveur des jeunes, des accomptes et des versements mensues de prime pour l'emploi
# reprise = zeros(taille) # TODO : reprise=J80
# Pcredit = P.credits_impots
# if hasattr(P.reductions_impots,'saldom'): Pcredit.saldom = P.reductions_impots.saldom
# credits_impot = Credits(Pcredit, table)
# Réduction d'impôt
# reductions = Reductions(IPnet, P.reductions_impots)

# def mcirra():
#    # impôt sur le revenu
#    mcirra = -((IMP<=-8)*IMP)
#    mciria = max_(0,(IMP>=0)*IMP)
# #        mciria = max_(0,(IMP>=0)*IMP - credimp_etranger - cont_rev_loc - ( f8to + f8tb + f8tc ))
#
#    # Dans l'ERFS, les prelevement libératoire sur les montants non déclarés
#    # sont intégrés. Pas possible de le recalculer.
#
#    # impot sur le revenu du foyer (hors prélèvement libératoire, revenus au quotient)
#    irpp   = -(mciria + ppetot - mcirra )


class jour_xyz(Variable):
    column = IntCol(default = 360)
    entity = FoyerFiscal
    label = u"Jours décomptés au titre de cette déclaration"
    definition_period = YEAR


###############################################################################
# # Initialisation de quelques variables utiles pour la suite
###############################################################################


class age(Variable):
    base_function = missing_value
    column = AgeCol(val_type = "age")
    entity = Individu
    label = u"Âge (en années) au premier jour du mois"
    definition_period = MONTH
    set_input = set_input_dispatch_by_period

    def formula(individu, period, parameters):
        def compare_periods(x, y):
            a = x[0]
            b = y[0]

            return periods.compare_period_start(a, b) or periods.compare_period_size(a, b)

        has_birth = individu.get_holder('date_naissance')._array is not None
        if not has_birth:
            has_age_en_mois = bool(individu.get_holder('age_en_mois')._array_by_period)
            if has_age_en_mois:
                return individu('age_en_mois', period) // 12

            # If age is known at the same day of another year, compute the new age from it.
            holder = individu.get_holder('age')
            start = period.start
            if holder._array_by_period is not None:
                for last_period, last_array in sorted(holder._array_by_period.iteritems(), cmp = compare_periods, reverse = True):
                    last_start = last_period.start
                    if last_start.day == start.day:
                        return last_array + int((start.year - last_start.year) +
                            (start.month - last_start.month) / 12)

        date_naissance = individu('date_naissance', period)
        return (datetime64(period.start) - date_naissance).astype('timedelta64[Y]')


class age_en_mois(Variable):
    base_function = missing_value
    column = AgeCol(val_type = "months")
    entity = Individu
    label = u"Âge (en mois)"
    definition_period = MONTH

    def formula(individu, period, parameters):

        def compare_periods(x, y):
            a = x[0]
            b = y[0]

            return periods.compare_period_start(a, b) or periods.compare_period_size(a, b)

        # If age_en_mois is known at the same day of another month, compute the new age_en_mois from it.
        holder = individu.get_holder('age_en_mois')
        start = period.start
        if holder._array_by_period is not None:
            for last_period, last_array in sorted(holder._array_by_period.iteritems(), cmp = compare_periods, reverse = True):
                last_start = last_period.start
                if last_start.day == start.day:
                    return last_array + ((start.year - last_start.year) * 12 + (start.month - last_start.month))

        has_birth = individu.get_holder('date_naissance')._array is not None
        if not has_birth:
            has_age = bool(individu.get_holder('age')._array_by_period)
            if has_age:
                return individu('age', period) * 12
        date_naissance = individu('date_naissance', period)
        return (datetime64(period.start) - date_naissance).astype('timedelta64[M]')


class nb_adult(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Nombre d'adulte(s) déclarants dans le foyer fiscal"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        celibataire_ou_divorce = foyer_fiscal('celibataire_ou_divorce', period)
        veuf = foyer_fiscal('veuf', period)

        return 2 * maries_ou_pacses + 1 * (celibataire_ou_divorce | veuf)


class nb_pac(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Nombre de personnes à charge dans le foyer fiscal"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        nbF = foyer_fiscal('nbF', period)
        nbJ = foyer_fiscal('nbJ', period)
        nbR = foyer_fiscal('nbR', period)

        return nbF + nbJ + nbR


class enfant_a_charge(Variable):
    column = BoolCol
    entity = Individu
    label = u"Enfant à charge non marié, de moins de 18 ans au 1er janvier de l'année de perception des" \
        u" revenus, ou né durant la même année, ou handicapés quel que soit son âge"
    definition_period = YEAR

    def formula(individu, period):
        janvier = period.first_month
        decembre = janvier.offset(11, 'month')
        age = individu('age', janvier)
        handicap = individu('handicap', decembre)
        is_pac = individu.has_role(FoyerFiscal.PERSONNE_A_CHARGE)

        return is_pac * ((age < 18) + handicap)


class nbF(Variable):
    cerfa_field = u'F'
    entity = FoyerFiscal
    column = FloatCol
    label = u"Nombre d'enfants à charge non mariés, qui ne sont pas en résidence alternée, de moins de 18 ans au 1er janvier de l'année de perception des" \
        u" revenus, ou nés durant la même année ou handicapés quel que soit leur âge"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        janvier = period.first_month

        enfant_a_charge = foyer_fiscal.members('enfant_a_charge', period)
        garde_alternee = foyer_fiscal.members('garde_alternee', janvier)
        return foyer_fiscal.sum(enfant_a_charge * not_(garde_alternee))


class nbG(Variable):
    cerfa_field = u'G'
    entity = FoyerFiscal
    column = FloatCol
    label = u"Nombre d'enfants qui ne sont pas en résidence alternée à charge titulaires de la carte d'invalidité."
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        janvier = period.first_month

        enfant_a_charge = foyer_fiscal.members('enfant_a_charge', period)
        garde_alternee = foyer_fiscal.members('garde_alternee', janvier)
        invalidite = foyer_fiscal.members('invalidite', janvier)
        return foyer_fiscal.sum(enfant_a_charge * not_(garde_alternee) * invalidite)


class nbH(Variable):
    cerfa_field = u'H'
    entity = FoyerFiscal
    column = FloatCol
    label = u"Nombre d'enfants à charge en résidence alternée, non mariés de moins de 18 ans au 1er janvier de l'année de perception des revenus, ou nés durant la même année ou handicapés quel que soit leur âge"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        janvier = period.first_month

        enfant_a_charge = foyer_fiscal.members('enfant_a_charge', period)
        garde_alternee = foyer_fiscal.members('garde_alternee', janvier)
        return foyer_fiscal.sum(enfant_a_charge * garde_alternee)


class nbI(Variable):
    cerfa_field = u'I'
    entity = FoyerFiscal
    column = FloatCol
    label = u"Nombre d'enfants à charge en résidence alternée titulaires de la carte d'invalidité"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        janvier = period.first_month

        enfant_a_charge = foyer_fiscal.members('enfant_a_charge', period)
        garde_alternee = foyer_fiscal.members('garde_alternee', janvier)
        invalidite = foyer_fiscal.members('invalidite', janvier)
        return foyer_fiscal.sum(enfant_a_charge * garde_alternee * invalidite)


class enfant_majeur_celibataire_sans_enfant(Variable):
    column = BoolCol
    entity = Individu
    label = u"Enfant majeur célibataire sans enfant"
    definition_period = YEAR

    def formula(individu, period):
        janvier = period.first_month

        age = individu('age', janvier)
        handicap = individu('handicap', janvier)
        is_pac = individu.has_role(FoyerFiscal.PERSONNE_A_CHARGE)

        return is_pac * (age >= 18) * not_(handicap)


class nbJ(Variable):
    cerfa_field = u'J'
    entity = FoyerFiscal
    label = u"Nombre d'enfants majeurs célibataires sans enfant"
    column = IntCol
    definition_period = YEAR

    def formula(foyer_fiscal, period):
        enfant_majeur_celibataire_sans_enfant = foyer_fiscal.members('enfant_majeur_celibataire_sans_enfant', period)
        return foyer_fiscal.sum(enfant_majeur_celibataire_sans_enfant)


class nombre_enfants_majeurs_celibataires_sans_enfant(Variable):
    entity = Menage
    label = u"Nombre d'enfants majeurs célibataires sans enfant"
    column = IntCol
    definition_period = YEAR

    def formula(menage, period):
        enfant_majeur_celibataire_sans_enfant = menage.members('enfant_majeur_celibataire_sans_enfant', period)
        return menage.sum(enfant_majeur_celibataire_sans_enfant)


class maries_ou_pacses(Variable):
    column = BoolCol
    entity = FoyerFiscal
    label = u"Déclarants mariés ou pacsés"
    definition_period = YEAR

    def formula(foyer_fiscal, period):
        statut_marital = foyer_fiscal.declarant_principal('statut_marital', period.first_month)
        marie_ou_pacse = (statut_marital == 1) | (statut_marital == 5)

        return marie_ou_pacse


class celibataire_ou_divorce(Variable):
    column = BoolCol
    entity = FoyerFiscal
    label = u"Déclarant célibataire ou divorcé"
    definition_period = YEAR

    def formula(foyer_fiscal, period):
        statut_marital = foyer_fiscal.declarant_principal('statut_marital', period.first_month)
        celibataire_ou_divorce = (statut_marital == 2) | (statut_marital == 3)

        return celibataire_ou_divorce


class veuf(Variable):
    column = BoolCol
    entity = FoyerFiscal
    label = u"Déclarant veuf"
    definition_period = YEAR

    def formula(foyer_fiscal, period):
        statut_marital = foyer_fiscal.declarant_principal('statut_marital', period.first_month)
        veuf = (statut_marital == 4)

        return veuf


class jeune_veuf(Variable):
    column = BoolCol
    entity = FoyerFiscal
    label = u"Déclarant jeune veuf"
    definition_period = YEAR

    def formula(foyer_fiscal, period):
        statut_marital = foyer_fiscal.declarant_principal('statut_marital', period.first_month)
        jeune_veuf = (statut_marital == 6)

        return jeune_veuf


###############################################################################
# # Revenus catégoriels
###############################################################################


class revenu_assimile_salaire(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenu imposé comme des salaires (salaires, mais aussi 3vj, 3vk)"
    definition_period = YEAR

    def formula(individu, period, parameters):
        salaire_imposable = individu('salaire_imposable', period, options = [ADD])
        chomage_imposable = individu('chomage_imposable', period, options = [ADD])

        return salaire_imposable + chomage_imposable


class revenu_assimile_salaire_apres_abattements(Variable):
    column = FloatCol
    entity = Individu
    label = u"Salaires et chômage imposables après abattements"
    definition_period = YEAR

    def formula(individu, period, parameters):
        revenu_assimile_salaire = individu('revenu_assimile_salaire', period)
        chomeur_longue_duree = individu('chomeur_longue_duree', period)
        frais_reels = individu('frais_reels', period)
        abatpro = parameters(period).impot_revenu.tspr.abatpro

        abattement_minimum = where(chomeur_longue_duree, abatpro.min2, abatpro.min)
        abatfor = round_(min_(max_(abatpro.taux * revenu_assimile_salaire, abattement_minimum), abatpro.max))
        return (
            (frais_reels > abatfor) * (revenu_assimile_salaire - frais_reels) +
            (frais_reels <= abatfor) * max_(0, revenu_assimile_salaire - abatfor)
            )


class revenu_activite_salariee(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenu d'activité salariée"
    definition_period = YEAR

    def formula(individu, period, parameters):
        salaire_imposable = individu('salaire_imposable', period, options = [ADD])

        return salaire_imposable


class revenu_activite_non_salariee(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenu d'activité non salariée"
    definition_period = YEAR

    def formula(individu, period, parameters):
        rpns_i = individu('rpns_individu', period)

        return rpns_i  # TODO: vérifier cette définition


class revenu_activite(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenus d'activités"
    definition_period = YEAR

    def formula(individu, period, parameters):
        ''' Revenus d'activités '''
        revenu_activite_non_salariee = individu('revenu_activite_non_salariee', period)
        revenu_activite_salariee = individu('revenu_activite_salariee', period)

        return revenu_activite_non_salariee + revenu_activite_salariee


class revenu_assimile_pension(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenu imposé comme des pensions (retraites, pensions alimentaires, etc.)"
    definition_period = YEAR

    def formula(individu, period):
        pensions_alimentaires_percues = individu('pensions_alimentaires_percues', period, options = [ADD])
        pensions_alimentaires_percues_decl = individu('pensions_alimentaires_percues_decl', period, options = [ADD])
        retraite_imposable = individu('retraite_imposable', period, options = [ADD])
        pension_invalidite = individu('pensions_invalidite', period, options = [ADD])

        return pensions_alimentaires_percues * pensions_alimentaires_percues_decl + retraite_imposable + pension_invalidite


class revenu_assimile_pension_apres_abattements(Variable):
    column = FloatCol
    entity = Individu
    label = u"Pensions après abattements"
    definition_period = YEAR

    def formula(individu, period, parameters):
        revenu_assimile_pension = individu('revenu_assimile_pension', period)
        abatpen = parameters(period).impot_revenu.tspr.abatpen

        #    TODO: problème car les pensions sont majorées au niveau du foyer
    #    d11 = ( AS + BS + CS + DS + ES +
    #            AO + BO + CO + DO + EO )
    #    penv2 = (d11-f11> abatpen.max)*(penv + (d11-f11-abatpen.max)) + (d11-f11<= abatpen.max)*penv
    #    Plus d'abatement de 20% en 2006
        return max_(0, revenu_assimile_pension - round_(max_(abatpen.taux * revenu_assimile_pension , abatpen.min)))


#    return max_(0, revenu_assimile_pension - min_(round_(max_(abatpen.taux*revenu_assimile_pension , abatpen.min)), abatpen.max))  le max se met au niveau du foyer

class indu_plaf_abat_pen(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Plafonnement de l'abattement de 10% sur les pensions du foyer"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        rev_pen_i = foyer_fiscal.members('revenu_assimile_pension', period)
        pen_net_i = foyer_fiscal.members('revenu_assimile_pension_apres_abattements', period)
        abatpen = parameters(period).impot_revenu.tspr.abatpen

        revenu_assimile_pension_apres_abattements = foyer_fiscal.sum(pen_net_i)
        revenu_assimile_pension = foyer_fiscal.sum(rev_pen_i)

        abat = revenu_assimile_pension - revenu_assimile_pension_apres_abattements
        return abat - min_(abat, abatpen.max)


class abattement_salaires_pensions(Variable):
    column = FloatCol
    entity = Individu
    label = u"Abattement de 20% sur les salaires et pensions, en vigueur jusqu'à 2006"
    end = '2005-12-31'
    definition_period = YEAR

    def formula(individu, period, parameters):
        revenu_assimile_salaire_apres_abattements = individu('revenu_assimile_salaire_apres_abattements', period)
        revenu_assimile_pension_apres_abattements = individu('revenu_assimile_pension_apres_abattements', period)
        abatsalpen = parameters(period).impot_revenu.tspr.abatsalpen

        return min_(abatsalpen.taux * max_(revenu_assimile_salaire_apres_abattements + revenu_assimile_pension_apres_abattements, 0), abatsalpen.max)


class retraite_titre_onereux(Variable):
    """Rentes viagères à titre onéreux (avant abattements)

    Annuel pour les impôts mais mensuel pour la base ressource des minimas sociaux donc mensuel.
    """
    calculate_output = calculate_output_add
    column = FloatCol
    entity = FoyerFiscal
    label = u"Rentes viagères (rentes à titre onéreux)"
    set_input = set_input_divide_by_period
    reference = u"http://fr.wikipedia.org/wiki/Rente_viagère"
    definition_period = MONTH

    def formula(foyer_fiscal, period, parameters):
        year = period.this_year
        f1aw = foyer_fiscal('f1aw', year)
        f1bw = foyer_fiscal('f1bw', year)
        f1cw = foyer_fiscal('f1cw', year)
        f1dw = foyer_fiscal('f1dw', year)

        return (f1aw + f1bw + f1cw + f1dw) / 12


class retraite_titre_onereux_net(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Rentes viagères après abattements"
    reference = u"http://www.lafinancepourtous.fr/Vie-professionnelle-et-retraite/Retraite/Epargne-retraite/La-rente-viagere/La-fiscalite-de-la-rente-viagere"  # noqa
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        f1aw = foyer_fiscal('f1aw', period)
        f1bw = foyer_fiscal('f1bw', period)
        f1cw = foyer_fiscal('f1cw', period)
        f1dw = foyer_fiscal('f1dw', period)
        abatviag = parameters(period).impot_revenu.tspr.abatviag

        return round_(abatviag.taux1 * f1aw + abatviag.taux2 * f1bw + abatviag.taux3 * f1cw + abatviag.taux4 * f1dw)


class traitements_salaires_pensions_rentes(Variable):
    column = FloatCol
    entity = Individu
    label = u"Traitements salaires pensions et rentes individuelles"
    definition_period = YEAR

    def formula(individu, period):
        revenu_assimile_salaire_apres_abattements = individu('revenu_assimile_salaire_apres_abattements', period)
        revenu_assimile_pension_apres_abattements = individu('revenu_assimile_pension_apres_abattements', period)
        abattement_salaires_pensions = individu('abattement_salaires_pensions', period)

        # Quand tspr est calculé sur une année glissante, retraite_titre_onereux_net est calculé sur l'année légale
        # correspondante.
        retraite_titre_onereux_net = individu.foyer_fiscal('retraite_titre_onereux_net', period.offset('first-of'))
        retraite_titre_onereux_net_declarant1 = retraite_titre_onereux_net * individu.has_role(FoyerFiscal.DECLARANT_PRINCIPAL)

        return revenu_assimile_salaire_apres_abattements + revenu_assimile_pension_apres_abattements - abattement_salaires_pensions + retraite_titre_onereux_net_declarant1


class rev_cat_pv(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu catégoriel - Plus-values"
    reference = "http://www.insee.fr/fr/methodes/default.asp?page=definitions/revenus-categoriesl.htm"
    definition_period = YEAR

    def formula_2013_01_01(foyer_fiscal, period, parameters):
        f3vg = foyer_fiscal('f3vg', period)
        f3vh = foyer_fiscal('f3vh', period)

        return f3vg - f3vh


class rev_cat_tspr(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu catégoriel - Traitements, salaires, pensions et rentes"
    reference = "http://www.insee.fr/fr/methodes/default.asp?page=definitions/revenus-categoriesl.htm"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        tspr_i = foyer_fiscal.members('traitements_salaires_pensions_rentes', period)
        indu_plaf_abat_pen = foyer_fiscal('indu_plaf_abat_pen', period)

        traitements_salaires_pensions_rentes = foyer_fiscal.sum(tspr_i)

        return traitements_salaires_pensions_rentes + indu_plaf_abat_pen


class deficit_rcm(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Deficit capitaux mobiliers"
    reference = "http://www.lefigaro.fr/impots/2008/04/25/05003-20080425ARTFIG00254-les-subtilites-des-revenus-de-capitaux-mobiliers-.php"
    definition_period = YEAR

    def formula_2009_01_01(foyer_fiscal, period, parameters):
        f2aa = foyer_fiscal('f2aa', period)
        f2al = foyer_fiscal('f2al', period)
        f2am = foyer_fiscal('f2am', period)
        f2an = foyer_fiscal('f2an', period)
        f2aq = foyer_fiscal('f2aq', period)
        f2ar = foyer_fiscal('f2ar', period)
        _P = parameters(period)

        return f2aa + f2al + f2am + f2an + f2aq + f2ar


class rev_cat_rvcm(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu catégoriel - Capitaux"
    reference = "http://www.insee.fr/fr/methodes/default.asp?page=definitions/revenus-categoriesl.htm"
    definition_period = YEAR

    def formula_2002_01_01(foyer_fiscal, period, parameters):
        """
        Revenus des valeurs et capitaux mobiliers
        """
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        deficit_rcm = foyer_fiscal('deficit_rcm', period)
        f2ch = foyer_fiscal('f2ch', period)
        f2dc = foyer_fiscal('f2dc', period)
        f2ts = foyer_fiscal('f2ts', period)
        f2ca = foyer_fiscal('f2ca', period)
        f2fu = foyer_fiscal('f2fu', period)
        f2go = foyer_fiscal('f2go', period)
        f2gr = foyer_fiscal('f2gr', period)
        f2tr = foyer_fiscal('f2tr', period)
        _P = parameters(period)
        finpfl = parameters(period).impot_revenu.autre.finpfl
        rvcm = parameters(period).impot_revenu.rvcm

        f2dc_bis = f2dc
        f2tr_bis = f2tr
        # # Calcul du revenu catégoriel
        # 1.2 Revenus des valeurs et capitaux mobiliers
        b12 = min_(f2ch, rvcm.abat_assvie * (1 + maries_ou_pacses))
        TOT1 = f2ch - b12  # c12
        # Part des frais s'imputant sur les revenus déclarés case DC
        den = ((f2dc_bis + f2ts) != 0) * (f2dc_bis + f2ts) + ((f2dc_bis + f2ts) == 0)
        F1 = f2ca / den * f2dc_bis  # f12
        # Revenus de capitaux mobiliers nets de frais, ouvrant droit à abattement
        # partie négative (à déduire des autres revenus nets de frais d'abattements
        g12a = -min_(f2dc_bis * (1 - rvcm.taux_abattement_capitaux_mobiliers) - F1, 0)
        # partie positive
        g12b = max_(f2dc_bis * (1 - rvcm.taux_abattement_capitaux_mobiliers) - F1, 0)
        rev = g12b + f2gr + f2fu * (1 - rvcm.taux_abattement_capitaux_mobiliers)

        # Abattements, limité au revenu
        h12 = rvcm.abatmob * (1 + maries_ou_pacses)
        TOT2 = max_(0, rev - h12)
        # i121= -min_(0,rev - h12)

        # Part des frais s'imputant sur les revenus déclarés ligne TS
        F2 = f2ca - F1
        TOT3 = (f2ts - F2) + f2go * rvcm.majGO + f2tr_bis - g12a

        DEF = deficit_rcm
        return max_(TOT1 + TOT2 + TOT3 - DEF, 0)

    def formula_2005_01_01(foyer_fiscal, period, parameters):
        """
        Revenus des valeurs et capitaux mobiliers
        """
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        deficit_rcm = foyer_fiscal('deficit_rcm', period)
        f2ch = foyer_fiscal('f2ch', period)
        f2dc = foyer_fiscal('f2dc', period)
        f2ts = foyer_fiscal('f2ts', period)
        f2ca = foyer_fiscal('f2ca', period)
        f2fu = foyer_fiscal('f2fu', period)
        f2go = foyer_fiscal('f2go', period)
        f2gr = foyer_fiscal('f2gr', period)
        f2tr = foyer_fiscal('f2tr', period)
        finpfl = parameters(period).impot_revenu.autre.finpfl
        rvcm = parameters(period).impot_revenu.rvcm

        # Add f2da to f2dc and f2ee to f2tr when no PFL
        f2dc_bis = f2dc
        f2tr_bis = f2tr
        # # Calcul du revenu catégoriel
        # 1.2 Revenus des valeurs et capitaux mobiliers
        b12 = min_(f2ch, rvcm.abat_assvie * (1 + maries_ou_pacses))
        TOT1 = f2ch - b12  # c12
        # Part des frais s'imputant sur les revenus déclarés case DC
        den = ((f2dc_bis + f2ts) != 0) * (f2dc_bis + f2ts) + ((f2dc_bis + f2ts) == 0)
        F1 = f2ca / den * f2dc_bis  # f12
        # Revenus de capitaux mobiliers nets de frais, ouvrant droit à abattement
        # partie négative (à déduire des autres revenus nets de frais d'abattements
        g12a = -min_(f2dc_bis * (1 - rvcm.taux_abattement_capitaux_mobiliers) - F1, 0)
        # partie positive
        g12b = max_(f2dc_bis * (1 - rvcm.taux_abattement_capitaux_mobiliers) - F1, 0)
        rev = g12b + f2gr + f2fu * (1 - rvcm.taux_abattement_capitaux_mobiliers)

        # Abattements, limité au revenu
        if period.start.date >= date(2012, 1, 01):
            h12 = 0
        else:
            h12 = rvcm.abatmob * (1 + maries_ou_pacses)
        TOT2 = max_(0, rev - h12)
        # i121= -min_(0,rev - h12)

        # Part des frais s'imputant sur les revenus déclarés ligne TS
        F2 = f2ca - F1
        TOT3 = (f2ts - F2) + f2go * rvcm.majGO + f2tr_bis - g12a

        DEF = deficit_rcm
        return max_(TOT1 + TOT2 + TOT3 - DEF, 0)

    # Cette formule a seulement été vérifiée jusqu'au 2015-12-31
    def formula_2013_01_01(foyer_fiscal, period, parameters):
        """
        Revenus des valeurs et capitaux mobiliers
        """
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        deficit_rcm = foyer_fiscal('deficit_rcm', period)
        f2ch = foyer_fiscal('f2ch', period)
        f2dc = foyer_fiscal('f2dc', period)
        f2ts = foyer_fiscal('f2ts', period)
        f2ca = foyer_fiscal('f2ca', period)
        f2fu = foyer_fiscal('f2fu', period)
        f2go = foyer_fiscal('f2go', period)
        f2tr = foyer_fiscal('f2tr', period)
        f2da = foyer_fiscal('f2da', period)
        f2ee = foyer_fiscal('f2ee', period)
        finpfl = parameters(period).impot_revenu.autre.finpfl
        rvcm = parameters(period).impot_revenu.rvcm

        # Add f2da to f2dc and f2ee to f2tr when no PFL
        f2dc_bis = f2dc + f2da  # TODO: l'abattement de 40% est déduit uniquement en l'absence de revenus déclarés case 2DA
        f2tr_bis = f2tr + f2ee

        # # Calcul du revenu catégoriel
        # 1.2 Revenus des valeurs et capitaux mobiliers
        b12 = min_(f2ch, rvcm.abat_assvie * (1 + maries_ou_pacses))
        TOT1 = f2ch - b12  # c12
        # Part des frais s'imputant sur les revenus déclarés case DC
        den = ((f2dc_bis + f2ts) != 0) * (f2dc_bis + f2ts) + ((f2dc_bis + f2ts) == 0)
        F1 = f2ca / den * f2dc_bis  # f12
        # Revenus de capitaux mobiliers nets de frais, ouvrant droit à abattement
        # partie négative (à déduire des autres revenus nets de frais d'abattements
        g12a = -min_(f2dc_bis * (1 - rvcm.taux_abattement_capitaux_mobiliers) - F1, 0)
        # partie positive
        g12b = max_(f2dc_bis * (1 - rvcm.taux_abattement_capitaux_mobiliers) - F1, 0)
        rev = g12b + f2fu * (1 - rvcm.taux_abattement_capitaux_mobiliers)

        # Abattements, limité au revenu
        h12 = 0
        TOT2 = max_(0, rev - h12)
        # i121= -min_(0,rev - h12)

        # Part des frais s'imputant sur les revenus déclarés ligne TS
        F2 = f2ca - F1
        TOT3 = (f2ts - F2) + f2go * rvcm.majGO + f2tr_bis - g12a

        DEF = deficit_rcm
        return max_(TOT1 + TOT2 + TOT3 - DEF, 0)


class rfr_rvcm(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"rfr_rvcm"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Abattements sur rvcm à réintégrer dans le revenu fiscal de référence
        '''
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        f2dc = foyer_fiscal('f2dc', period)
        f2ts = foyer_fiscal('f2ts', period)
        f2ca = foyer_fiscal('f2ca', period)
        f2gr = foyer_fiscal('f2gr', period)
        f2fu = foyer_fiscal('f2fu', period)
        f2da = foyer_fiscal('f2da', period)
        finpfl = parameters(period).impot_revenu.autre.finpfl
        rvcm = parameters(period).impot_revenu.rvcm

        if finpfl:
            f2dc_bis = f2dc + f2da
        else:
            f2dc_bis = f2dc

        # Calcul de i121
        # Part des frais s'imputant sur les revenus déclarés case DC
        den = ((f2dc_bis + f2ts) != 0) * (f2dc_bis + f2ts) + ((f2dc_bis + f2ts) == 0)
        F1 = f2ca / den * f2dc_bis  # f12
        # Revenus de capitaux mobiliers nets de frais, ouvrant droit à abattement
        # partie positive
        g12b = max_(f2dc_bis * (1 - rvcm.taux_abattement_capitaux_mobiliers) - F1, 0)
        rev = g12b + f2gr + f2fu * (1 - rvcm.taux_abattement_capitaux_mobiliers)

        # Abattements, limité au revenu
        if period.start.date >= date(2012, 1, 01):
            h12 = 0
        else:
            h12 = rvcm.abatmob * (1 + maries_ou_pacses)
        i121 = - min_(0, rev - h12)
        return max_((rvcm.taux_abattement_capitaux_mobiliers) * (f2dc_bis + f2fu) - i121, 0)


class rev_cat_rfon(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu catégoriel - Foncier"
    reference = "http://www.insee.fr/fr/methodes/default.asp?page=definitions/revenus-categoriesl.htm"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        """
        Revenus fonciers
        """
        f4ba = foyer_fiscal('f4ba', period)
        f4bb = foyer_fiscal('f4bb', period)
        f4bc = foyer_fiscal('f4bc', period)
        f4bd = foyer_fiscal('f4bd', period)
        f4be = foyer_fiscal('f4be', period)
        microfoncier = parameters(period).impot_revenu.rpns.micro.microfoncier

        # # Calcul du revenu catégoriel
        if ((f4be != 0) & ((f4ba != 0) | (f4bb != 0) | (f4bc != 0))).any():
            log.error(("Problème de déclarations des revenus : incompatibilité de la déclaration des revenus fonciers (f4ba, f4bb, f4bc) et microfonciers (f4be)"))

        a13 = f4ba + f4be - microfoncier.taux * f4be * (f4be <= microfoncier.max)
        b13 = f4bb
        c13 = a13 - b13
        d13 = f4bc
        e13 = c13 - d13 * (c13 >= 0)
        f13 = f4bd * (e13 >= 0)
        g13 = max_(0, e13 - f13)
        rev_cat_rfon = (c13 >= 0) * (g13 + e13 * (e13 < 0)) - (c13 < 0) * d13
        return rev_cat_rfon


class rev_cat_rpns(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu catégoriel - Revenus personnels non salariés"
    reference = "http://www.insee.fr/fr/methodes/default.asp?page=definitions/revenus-categoriesl.htm"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Revenus personnels non salariés
        'foy'
        '''
        nbnc_pvce_i = foyer_fiscal.members('nbnc_pvce', period)
        mbic_mvct = foyer_fiscal('mbic_mvct', period)
        rpns_i = foyer_fiscal.members('rpns_individu', period)
        defrag = foyer_fiscal('defrag', period)
        defacc = foyer_fiscal('defacc', period)
        defncn = foyer_fiscal('defncn', period)
        defmeu = foyer_fiscal('defmeu', period)

        return (
            foyer_fiscal.sum(rpns_i) -
            foyer_fiscal.sum(nbnc_pvce_i) - defrag - defncn - defacc - defmeu - mbic_mvct
            )


class rev_cat(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenus catégoriels"
    reference = "http://www.insee.fr/fr/methodes/default.asp?page=definitions/revenus-categoriesl.htm"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Revenus Categoriels
        '''
        rev_cat_tspr = foyer_fiscal('rev_cat_tspr', period)
        rev_cat_rvcm = foyer_fiscal('rev_cat_rvcm', period)
        rev_cat_rfon = foyer_fiscal('rev_cat_rfon', period)
        rev_cat_rpns = foyer_fiscal('rev_cat_rpns', period)
        rev_cat_pv = foyer_fiscal('rev_cat_pv', period)

        return rev_cat_tspr + rev_cat_rvcm + rev_cat_rfon + rev_cat_rpns + rev_cat_pv


###############################################################################
# # Déroulé du calcul de l'irpp
###############################################################################


class deficit_ante(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Déficit global antérieur"
    reference = "http://impotsurlerevenu.org/declaration-de-revenus-fonciers-2044/796-deficits-anterieurs-restant-a-imputer-cadre-450.php"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Déficits antérieurs
        '''
        f6fa = foyer_fiscal('f6fa', period)
        f6fb = foyer_fiscal('f6fb', period)
        f6fc = foyer_fiscal('f6fc', period)
        f6fd = foyer_fiscal('f6fd', period)
        f6fe = foyer_fiscal('f6fe', period)
        f6fl = foyer_fiscal('f6fl', period)

        return f6fa + f6fb + f6fc + f6fd + f6fe + f6fl


class rbg(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu brut global"
    reference = "http://www.documentissime.fr/dossiers-droit-pratique/dossier-19-l-impot-sur-le-revenu-les-modalites-generales-d-imposition/la-determination-du-revenu-imposable/le-revenu-brut-global.html"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''Revenu brut global
        '''
        rev_cat = foyer_fiscal('rev_cat', period)
        deficit_ante = foyer_fiscal('deficit_ante', period)
        f6gh = foyer_fiscal('f6gh', period)
        nbic_impm_i = foyer_fiscal.members('nbic_impm', period)
        nacc_pvce_i = foyer_fiscal.members('nacc_pvce', period)
        cga = parameters(period).impot_revenu.rpns.cga_taux2

        # (Total 17)
        # sans les revenus au quotient
        nacc_pvce = foyer_fiscal.sum(nacc_pvce_i)
        return max_(0,
                    rev_cat + f6gh + (foyer_fiscal.sum(nbic_impm_i) + nacc_pvce) * (1 + cga) - deficit_ante)


class csg_deduc_patrimoine(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Csg déductible sur le patrimoine"
    reference = "http://www.impots.gouv.fr/portal/dgi/public/particuliers.impot?pageId=part_ctrb_soc&typePage=cpr02&sfid=503&espId=1&communaute=1&impot=CS"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        CSG déductible sur les revenus du patrimoine
        http://bofip.impots.gouv.fr/bofip/887-PGP
        '''
        f6de = foyer_fiscal('f6de', period)

        return max_(f6de, 0)


class csg_deduc_patrimoine_simulated(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Csg déductible sur le patrimoine simulée"
    reference = "http://www.impots.gouv.fr/portal/dgi/public/particuliers.impot?pageId=part_ctrb_soc&typePage=cpr02&sfid=503&espId=1&communaute=1&impot=CS"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Cette fonction simule le montant mentionné dans la case f6de de la déclaration 2042
        http://bofip.impots.gouv.fr/bofip/887-PGP
        '''
        rev_cat_rfon = foyer_fiscal('rev_cat_rfon', period)
        rev_cap_bar = foyer_fiscal('rev_cap_bar', period)
        retraite_titre_onereux = foyer_fiscal('retraite_titre_onereux', period)
        taux = parameters(period).csg.capital.deduc

        patrimoine_deduc = rev_cat_rfon + rev_cap_bar + retraite_titre_onereux
        return taux * patrimoine_deduc


class csg_deduc(Variable):  # f6de
    column = FloatCol
    entity = FoyerFiscal
    label = u"Csg déductible sur le patrimoine"
    reference = "http://www.impots.gouv.fr/portal/dgi/public/particuliers.impot?pageId=part_ctrb_soc&typePage=cpr02&sfid=503&espId=1&communaute=1&impot=CS"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        ''' CSG déductible '''
        rbg = foyer_fiscal('rbg', period)
        csg_deduc_patrimoine = foyer_fiscal('csg_deduc_patrimoine', period)

        # min_(f6de, max_(rbg, 0))
        return min_(csg_deduc_patrimoine, max_(rbg, 0))


class rng(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu net global"
    reference = "http://impotsurlerevenu.org/definitions/114-revenu-net-global.php"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        ''' Revenu net global (total 20) '''
        rbg = foyer_fiscal('rbg', period)
        csg_deduc = foyer_fiscal('csg_deduc', period)
        charges_deduc = foyer_fiscal('charges_deduc', period)

        return max_(0, rbg - csg_deduc - charges_deduc)


class rni(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu net imposable"
    reference = "http://impotsurlerevenu.org/definitions/115-revenu-net-imposable.php"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        ''' Revenu net imposable ou déficit à reporter'''
        rng = foyer_fiscal('rng', period)
        abat_spe = foyer_fiscal('abat_spe', period)

        return rng - abat_spe


class ir_brut(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Impôt sur le revenu brut avant non imposabilité et plafonnement du quotient"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        nbptr = foyer_fiscal('nbptr', period)
        taux_effectif = foyer_fiscal('taux_effectif', period)
        rni = foyer_fiscal('rni', period)
        bareme = parameters(period).impot_revenu.bareme

        return (taux_effectif == 0) * nbptr * bareme.calc(rni / nbptr) + taux_effectif * rni


class ir_ss_qf(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Impôt sans quotient familial"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Impôt sans quotient familial
        '''
        rni = foyer_fiscal('rni', period)
        nb_adult = foyer_fiscal('nb_adult', period)
        bareme = parameters(period).impot_revenu.bareme

        A = bareme.calc(rni / nb_adult)
        return nb_adult * A


class ir_plaf_qf(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Impôt après plafonnement du quotient familial et réduction complémentaire"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Impôt après plafonnement du quotient familial et réduction complémentaire
        '''
        ir_brut = foyer_fiscal('ir_brut', period)
        ir_ss_qf = foyer_fiscal('ir_ss_qf', period)
        nb_adult = foyer_fiscal('nb_adult', period)
        nb_pac = foyer_fiscal('nb_pac', period)
        nbptr = foyer_fiscal('nbptr', period)
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        veuf = foyer_fiscal('veuf', period)
        jeune_veuf = foyer_fiscal('jeune_veuf', period)
        celibataire_ou_divorce = foyer_fiscal('celibataire_ou_divorce', period)
        caseE = foyer_fiscal('caseE', period)
        caseF = foyer_fiscal('caseF', period)
        caseG = foyer_fiscal('caseG', period)
        caseH = foyer_fiscal('caseH', period)
        caseK = foyer_fiscal('caseK', period)
        caseN = foyer_fiscal('caseN', period)
        caseP = foyer_fiscal('caseP', period)
        caseS = foyer_fiscal('caseS', period)
        caseT = foyer_fiscal('caseT', period.first_month)
        caseW = foyer_fiscal('caseW', period)
        nbF = foyer_fiscal('nbF', period)
        nbG = foyer_fiscal('nbG', period)
        nbH = foyer_fiscal('nbH', period)
        nbI = foyer_fiscal('nbI', period)
        nbR = foyer_fiscal('nbR', period)
        plafond_qf = parameters(period).impot_revenu.plafond_qf

        A = ir_ss_qf
        I = ir_brut

        aa0 = (nbptr - nb_adult) * 2  # nombre de demi part excédant nbadult
        # on dirait que les impôts font une erreur sur aa1 (je suis obligé de
        # diviser par 2)
        aa1 = min_((nbptr - 1) * 2, 2) / 2  # deux première demi part excédants une part
        aa2 = max_((nbptr - 2) * 2, 0)  # nombre de demi part restantes
        # celibataire_ou_divorce parents isolés
        condition61 = celibataire_ou_divorce & caseT
        B1 = plafond_qf.celib_enf * aa1 + plafond_qf.maries_ou_pacses * aa2
        # tous les autres
        B2 = plafond_qf.maries_ou_pacses * aa0  # si autre
        # celibataire_ou_divorce, veufs (non jeune_veuf) vivants seuls et autres conditions

        # TODO: année en dur... pour caseH
        condition63 = (celibataire_ou_divorce | (veuf & not_(jeune_veuf))) & not_(caseN) & (nb_pac == 0) & (caseK | caseE) & (caseH < 1981)
        B3 = plafond_qf.celib

        B = B1 * condition61 + \
            B2 * (not_(condition61 | condition63)) + \
            B3 * (condition63 & not_(condition61))
        C = max_(0, A - B)
        # Impôt après plafonnement
        IP0 = max_(I, C)

        # 6.2 réduction d'impôt pratiquée sur l'impot après plafonnement et le cas particulier des DOM
        # pas de réduction complémentaire
        condition62a = (I >= C)
        # réduction complémentaire
        condition62b = (I < C)
        # celibataire_ou_divorce veuf
        condition62caa0 = (celibataire_ou_divorce | (veuf & not_(jeune_veuf)))
        condition62caa1 = (nb_pac == 0) & (caseP | caseG | caseF | caseW)
        condition62caa2 = caseP & ((nbF - nbG > 0) | (nbH - nbI > 0))
        condition62caa3 = not_(caseN) & (caseE | caseK) & (caseH >= 1981)
        condition62caa = condition62caa0 & (condition62caa1 | condition62caa2 | condition62caa3)
        # marié pacs
        condition62cab = (maries_ou_pacses | jeune_veuf) & caseS & not_(caseP | caseF)

        condition62ca = (condition62caa | condition62cab)

        # plus de 590 euros si on a des plus de
        condition62cb = ((nbG + nbR + nbI) > 0) | caseP | caseF
        D = plafond_qf.reduc_postplafond * (condition62ca + ~condition62ca * condition62cb * (
            1 * caseP + 1 * caseF + nbG + nbR + nbI / 2))

        E = max_(0, A - I - B)
        Fo = D * (D <= E) + E * (E < D)
        IP1 = IP0 - Fo

        # TODO: 6.3 Cas particulier: Contribuables domiciliés dans les DOM.
        # conditionGuadMarReu =
        # conditionGuyane=
        # conitionDOM = conditionGuadMarReu | conditionGuyane
        # postplafGuadMarReu = 5100
        # postplafGuyane = 6700
        # IP2 = IP1 - conditionGuadMarReu*min( postplafGuadMarReu,.3*IP1)  - conditionGuyane*min(postplafGuyane,.4*IP1)

        # Récapitulatif

        return condition62a * IP0 + condition62b * IP1  # IP2 si DOM


class avantage_qf(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Avantage quotient familial"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        ir_ss_qf = foyer_fiscal('ir_ss_qf', period)
        ir_plaf_qf = foyer_fiscal('ir_plaf_qf', period)

        return ir_ss_qf - ir_plaf_qf


class decote(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"décote"
    definition_period = YEAR

    def formula_2015_01_01(foyer_fiscal, period, parameters):
        ir_plaf_qf = foyer_fiscal('ir_plaf_qf', period)
        nb_adult = foyer_fiscal('nb_adult', period)
        decote_seuil_celib = parameters(period).impot_revenu.decote.seuil_celib
        decote_seuil_couple = parameters(period).impot_revenu.decote.seuil_couple
        decote_celib = (ir_plaf_qf < 4 / 3 * decote_seuil_celib) * (decote_seuil_celib - 3 / 4 * ir_plaf_qf)
        decote_couple = (ir_plaf_qf < 4 / 3 * decote_seuil_couple) * (decote_seuil_couple - 3 / 4 * ir_plaf_qf)

        return (nb_adult == 1) * decote_celib + (nb_adult == 2) * decote_couple

    def formula_2014_01_01(foyer_fiscal, period, parameters):
        ir_plaf_qf = foyer_fiscal('ir_plaf_qf', period)
        nb_adult = foyer_fiscal('nb_adult', period)
        decote_seuil_celib = parameters(period).impot_revenu.decote.seuil_celib
        decote_seuil_couple = parameters(period).impot_revenu.decote.seuil_couple
        decote_celib = (ir_plaf_qf < decote_seuil_celib) * (decote_seuil_celib - ir_plaf_qf)
        decote_couple = (ir_plaf_qf < decote_seuil_couple) * (decote_seuil_couple - ir_plaf_qf)

        return (nb_adult == 1) * decote_celib + (nb_adult == 2) * decote_couple

    def formula_2001_01_01(foyer_fiscal, period, parameters):
        ir_plaf_qf = foyer_fiscal('ir_plaf_qf', period)
        decote = parameters(period).impot_revenu.decote

        return (ir_plaf_qf < decote.seuil) * (decote.seuil - ir_plaf_qf) * 0.5


class decote_gain_fiscal(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Gain fiscal de la décote/Décote au sens Dgfip tel que sur la feuille d'impôt"
    definition_period = YEAR

    def formula_1982_01_01(foyer_fiscal, period, parameters):
        '''
        Renvoie le gain fiscal du à la décote
        '''
        decote = foyer_fiscal('decote', period)
        ir_plaf_qf = foyer_fiscal('ir_plaf_qf', period)

        return min_(decote, ir_plaf_qf)


class nat_imp(Variable):
    column = BoolCol(default = False)
    entity = FoyerFiscal
    label = u"nat_imp"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Renvoie True si le foyer est imposable, False sinon
        '''
        iai = foyer_fiscal('iai', period)
        credits_impot = foyer_fiscal('credits_impot', period)
        cehr = foyer_fiscal('cehr', period)

        # def _nat_imp(rni, nbptr, non_imposable = law.impot_revenu.non_imposable):
        # seuil = non_imposable.seuil + (nbptr - 1)*non_imposable.supp
        return (iai - credits_impot + cehr) > 0


class ip_net(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Impôt sur le revenu après décote"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        irpp après décote
        '''
        ir_plaf_qf = foyer_fiscal('ir_plaf_qf', period)
        cncn_info_i = foyer_fiscal.members('cncn_info', period)
        decote = foyer_fiscal('decote', period)
        taux = parameters(period).impot_revenu.rpns.taux16

        return max_(0, ir_plaf_qf + foyer_fiscal.sum(cncn_info_i) * taux - decote)


class iaidrdi(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Impôt après imputation des réductions d'impôt"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Impôt après imputation des réductions d'impôt
        '''
        ip_net = foyer_fiscal('ip_net', period)
        reductions = foyer_fiscal('reductions', period)

        return ip_net - reductions


class cont_rev_loc(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Contribution sur les revenus locatifs"
    definition_period = YEAR

    def formula_2001_01_01(foyer_fiscal, period, parameters):
        '''
        Contribution sur les revenus locatifs
        '''
        f4bl = foyer_fiscal('f4bl', period)
        crl = parameters(period).impot_revenu.crl

        return round_(crl.taux * (f4bl >= crl.seuil) * f4bl)


class teicaa(Variable):  # f5rm
    column = FloatCol
    entity = FoyerFiscal
    label = u"Taxe exceptionelle sur l'indemnité compensatrice des agents d'assurance"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        """
        Taxe exceptionelle sur l'indemnité compensatrice des agents d'assurance
        """
        bareme = parameters(period).impot_revenu.teicaa

        f5qm = foyer_fiscal.declarant_principal('f5qm', period)
        f5rm = foyer_fiscal.conjoint('f5qm', period)

        return bareme.calc(f5qm) + bareme.calc(f5rm)


class assiette_vente(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Assiette régime microsociale pour les ventes"
    definition_period = YEAR

    def formula_2009_01_01(foyer_fiscal, period, parameters):
        '''
        Assiette régime microsociale pour les ventes
        '''
        ebic_impv_i = foyer_fiscal.members('ebic_impv', period)

        return foyer_fiscal.sum(ebic_impv_i)


class assiette_service(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Assiette régime microsociale pour les prestations et services"
    definition_period = YEAR

    def formula_2009_01_01(foyer_fiscal, period, parameters):
        '''
        Assiette régime microsociale pour les prestations et services
        '''
        ebic_imps_i = foyer_fiscal.members('ebic_imps', period)

        return foyer_fiscal.sum(ebic_imps_i)

    # P = _P.impot_revenu.rpns.micro.microentreprise
    # assert (ebic_imps <= P.servi.max)


class assiette_proflib(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Assiette régime microsociale pour les professions libérales"
    definition_period = YEAR

    def formula_2009_01_01(foyer_fiscal, period, parameters):
        '''
        Assiette régime microsocial pour les professions libérales
        '''
        ebnc_impo_i = foyer_fiscal.members('ebnc_impo', period)
        P = parameters(period).impot_revenu.rpns.micro

        # TODO: distinction RSI/CIPAV (pour les cotisations sociales)
        # http://vosdroits.service-public.fr/professionnels-entreprises/F23267.xhtml
        return foyer_fiscal.sum(ebnc_impo_i)

    # assert (ebnc_impo <= P.specialbnc.max)


class microsocial(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Assiette régime microsociale totale"
    reference = "http://fr.wikipedia.org/wiki/R%C3%A9gime_micro-social"
    definition_period = YEAR

    def formula_2009_01_01(foyer_fiscal, period, parameters):
        assiette_service = foyer_fiscal('assiette_service', period)
        assiette_vente = foyer_fiscal('assiette_vente', period)
        assiette_proflib = foyer_fiscal('assiette_proflib', period)
        microsocial = parameters(period).impot_revenu.rpns.microsocial

        return (
            assiette_service * microsocial.servi +
            assiette_vente * microsocial.vente + assiette_proflib * microsocial.bnc
            )


class microentreprise(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"microentreprise"
    definition_period = YEAR

    def formula_2009_01_01(foyer_fiscal, period, parameters):
        ebnc_impo_i = foyer_fiscal.members('ebnc_impo', period)
        ebic_imps_i = foyer_fiscal.members('ebic_imps', period)
        ebic_impv_i = foyer_fiscal.members('ebic_impv', period)
        micro = parameters(period).impot_revenu.rpns.micro
        ebnc_impo = foyer_fiscal.sum(ebnc_impo_i)
        ebic_imps = foyer_fiscal.sum(ebic_imps_i)
        ebic_impv = foyer_fiscal.sum(ebic_impv_i)
        return (
            ebnc_impo * (1 - micro.specialbnc.taux) +
            ebic_imps * (1 - micro.microentreprise.taux_prestations_de_services) +
            ebic_impv * (1 - micro.microentreprise.taux_ventes_de_marchandises)
            )


class plus_values(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Taxation des plus_values"
    definition_period = YEAR

    def formula_2007_01_01(foyer_fiscal, period, parameters):  # f3sd is in f3vd holder
        """
        Taxation des plus values
        TODO: 2013 f3Vg au barème / tout refaire
        """
        f3vg = foyer_fiscal('f3vg', period)
        f3vh = foyer_fiscal('f3vh', period)
        f3vl = foyer_fiscal('f3vl', period)
        f3vm = foyer_fiscal('f3vm', period)
        rpns_pvce_i = foyer_fiscal.members('rpns_pvce', period)
        _P = parameters(period)
        plus_values = parameters(period).impot_revenu.plus_values

        rpns_pvce = foyer_fiscal.sum(rpns_pvce_i)
        f3vd = foyer_fiscal.declarant_principal('f3vd', period)
        f3sd = foyer_fiscal.conjoint('f3vd', period)
        f3vi = foyer_fiscal.declarant_principal('f3vi', period)
        f3si = foyer_fiscal.conjoint('f3vi', period)
        f3vf = foyer_fiscal.declarant_principal('f3vf', period)
        f3sf = foyer_fiscal.conjoint('f3vf', period)
        #  TODO: remove this todo use sum for all fields after checking
            # revenus taxés à un taux proportionnel
        rdp = max_(0, f3vg - f3vh) + f3vl + rpns_pvce + f3vm + f3vi + f3vf
        out = (plus_values.pvce * rpns_pvce +
               plus_values.taux1 * max_(0, f3vg - f3vh) +
               plus_values.taux_pv_mob_pro * f3vl +
               plus_values.pea.taux_avant_2_ans * f3vm +
               plus_values.taux3 * f3vi +
               plus_values.taux4 * f3vf)

        return round_(out)

    def formula_2008_01_01(foyer_fiscal, period, parameters):  # f3sd is in f3vd holder
        """
        Taxation des plus value
        TODO:  2013 f3Vg au barème / tout refaire
        """
        f3vg = foyer_fiscal('f3vg', period)
        f3vh = foyer_fiscal('f3vh', period)
        f3vl = foyer_fiscal('f3vl', period)
        f3vm = foyer_fiscal('f3vm', period)
        rpns_pvce_i = foyer_fiscal.members('rpns_pvce', period)
        plus_values = parameters(period).impot_revenu.plus_values

        rpns_pvce = foyer_fiscal.sum(rpns_pvce_i)
        f3vd = foyer_fiscal.declarant_principal('f3vd', period)
        f3sd = foyer_fiscal.conjoint('f3vd', period)
        f3vi = foyer_fiscal.declarant_principal('f3vi', period)
        f3si = foyer_fiscal.conjoint('f3vi', period)
        f3vf = foyer_fiscal.declarant_principal('f3vf', period)
        f3sf = foyer_fiscal.conjoint('f3vf', period)
        #  TODO: remove this todo use sum for all fields after checking
            # revenus taxés à un taux proportionnel
        rdp = max_(0, f3vg - f3vh) + f3vl + rpns_pvce + f3vm + f3vi + f3vf
        out = (plus_values.pvce * rpns_pvce +
               plus_values.taux1 * max_(0, f3vg - f3vh) +
               plus_values.taux_pv_mob_pro * f3vl +
               plus_values.pea.taux_avant_2_ans * f3vm +
               plus_values.taux3 * f3vi +
               plus_values.taux4 * f3vf)
            # revenus taxés à un taux proportionnel
        rdp += f3vd
        out += plus_values.taux1 * f3vd

        return round_(out)

    def formula_2012_01_01(foyer_fiscal, period, parameters):  # f3sd is in f3vd holder
        """
        Taxation des plus value
        TODO: 2013 f3Vg au barème / tout refaire
        """
        f3vg = foyer_fiscal('f3vg', period)
        f3vh = foyer_fiscal('f3vh', period)
        f3vl = foyer_fiscal('f3vl', period)
        f3vt = foyer_fiscal('f3vt', period)
        f3vm = foyer_fiscal('f3vm', period)
        rpns_pvce_i = foyer_fiscal.members('rpns_pvce', period)
        plus_values = parameters(period).impot_revenu.plus_values

        rpns_pvce = foyer_fiscal.sum(rpns_pvce_i)
        f3vd = foyer_fiscal.declarant_principal('f3vd', period)
        f3sd = foyer_fiscal.conjoint('f3vd', period)
        f3vi = foyer_fiscal.declarant_principal('f3vi', period)
        f3si = foyer_fiscal.conjoint('f3vi', period)
        f3vf = foyer_fiscal.declarant_principal('f3vf', period)
        f3sf = foyer_fiscal.conjoint('f3vf', period)
        # TODO: remove this todo use sum for all fields after checking
        # revenus taxés à un taux proportionnel
        rdp = max_(0, f3vg - f3vh) + f3vl + rpns_pvce + f3vm + f3vi + f3vf
        out = (plus_values.pvce * rpns_pvce +
               plus_values.taux1 * max_(0, f3vg - f3vh) +
               plus_values.taux_pv_mob_pro * f3vl +
               plus_values.pea.taux_avant_2_ans * f3vm +
               plus_values.taux3 * f3vi +
               plus_values.taux4 * f3vf)
        # revenus taxés à un taux proportionnel
        rdp += f3vd
        out += plus_values.taux1 * f3vd
        #        out = plus_values.taux2 * f3vd + plus_values.taux3 * f3vi + plus_values.taux4 * f3vf + plus_values.taux1 *max_(
        #            0, f3vg - f3vh)
        out = (plus_values.taux2 * (f3vd + f3sd) + plus_values.taux3 * (f3vi + f3si) +
            plus_values.taux4 * (f3vf + f3sf) + plus_values.taux1 * max_(0, f3vg - f3vh) + plus_values.pvce * rpns_pvce)
                # TODO: chek this rpns missing ?
        return round_(out)

    # Cette formule a seulement été vérifiée jusqu'au 2015-12-31
    def formula_2013_01_01(foyer_fiscal, period, parameters):  # f3sd is in f3vd holder
        """
        Taxation des plus value
        TODO: 2013 f3Vg au barème / tout refaire
        """
        f3vg = foyer_fiscal('f3vg', period)
        f3vh = foyer_fiscal('f3vh', period)
        f3vl = foyer_fiscal('f3vl', period)
        f3vm = foyer_fiscal('f3vm', period)
        f3vt = foyer_fiscal('f3vt', period)
        f3sa = foyer_fiscal('f3sa', period)
        rpns_pvce_i = foyer_fiscal.members('rpns_pvce', period)
        _P = parameters(period)
        plus_values = parameters(period).impot_revenu.plus_values

        rpns_pvce = foyer_fiscal.sum(rpns_pvce_i)
        f3vd = foyer_fiscal.declarant_principal('f3vd', period)
        f3sd = foyer_fiscal.conjoint('f3vd', period)
        f3vi = foyer_fiscal.declarant_principal('f3vi', period)
        f3si = foyer_fiscal.conjoint('f3vi', period)
        f3vf = foyer_fiscal.declarant_principal('f3vf', period)
        f3sf = foyer_fiscal.conjoint('f3vf', period)
        #  TODO: remove this todo use sum for all fields after checking
        # revenus taxés à un taux proportionnel
        rdp = max_(0, f3vg - f3vh) + f3vl + rpns_pvce + f3vm + f3vi + f3vf
        out = (plus_values.pvce * rpns_pvce +
               plus_values.taux1 * max_(0, f3vg - f3vh) +
               plus_values.taux_pv_mob_pro * f3vl +
               plus_values.pea.taux_avant_2_ans * f3vm +
               plus_values.taux3 * f3vi +
               plus_values.taux4 * f3vf)

        # revenus taxés à un taux proportionnel
        rdp += f3vd
        out += plus_values.taux1 * f3vd
        #  out = plus_values.taux2 * f3vd + plus_values.taux3 * f3vi + plus_values.taux4 * f3vf + plus_values.taux1 * max_(
        #          0, f3vg - f3vh)
        out = (plus_values.taux2 * (f3vd + f3sd) + plus_values.taux3 * (f3vi + f3si) +
            plus_values.taux4 * (f3vf + f3sf) + plus_values.taux1 * max_(0, - f3vh) + plus_values.pvce * (rpns_pvce + f3sa))
        # TODO: chek this 3VG
        return round_(out)


class iai(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Impôt avant imputations de l'impôt sur le revenu"
    reference = "http://forum-juridique.net-iris.fr/finances-fiscalite-assurance/43963-declaration-impots.html"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        impôt avant imputation de l'irpp
        '''
        iaidrdi = foyer_fiscal('iaidrdi', period)
        plus_values = foyer_fiscal('plus_values', period)
        cont_rev_loc = foyer_fiscal('cont_rev_loc', period)
        teicaa = foyer_fiscal('teicaa', period)

        return iaidrdi + plus_values + cont_rev_loc + teicaa


class cehr(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Contribution exceptionnelle sur les hauts revenus"
    reference = "http://www.legifrance.gouv.fr/affichCode.do?cidTexte=LEGITEXT000006069577&idSectionTA=LEGISCTA000025049019"
    definition_period = YEAR

    def formula_2011_01_01(foyer_fiscal, period, parameters):
        '''
        Contribution exceptionnelle sur les hauts revenus
        'foy'
        '''
        rfr = foyer_fiscal('rfr', period)
        nb_adult = foyer_fiscal('nb_adult', period)
        bareme = parameters(period).impot_revenu.cehr

        return bareme.calc(rfr / nb_adult) * nb_adult
        # TODO: Gérer le II.-1 du lissage interannuel ? (problème de non recours)


class irpp(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Impôt sur le revenu des personnes physiques"
    reference = "http://www.impots.gouv.fr/portal/dgi/public/particuliers.impot?pageId=part_impot_revenu&espId=1&impot=IR&sfid=50"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Montant après seuil de recouvrement (hors ppe)
        '''
        iai = foyer_fiscal('iai', period)
        credits_impot = foyer_fiscal('credits_impot', period)
        cehr = foyer_fiscal('cehr', period)
        P = parameters(period).impot_revenu.recouvrement

        pre_result = iai - credits_impot + cehr
        return (
            (iai > P.seuil) * (
                (pre_result < P.min) * (pre_result > 0) * iai * 0 +
                ((pre_result <= 0) + (pre_result >= P.min)) * (- pre_result)
                ) +
            (iai <= P.seuil) * (
                (pre_result < 0) * (-pre_result) + (pre_result >= 0) * 0 * iai)
            )


class foyer_impose(Variable):
    column = BoolCol(default = False)
    entity = FoyerFiscal
    label = u"Le foyer fiscal est imposé"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        irpp = foyer_fiscal('irpp', period)
        return (irpp < 0)

###############################################################################
# # Autres totaux utiles pour la suite
###############################################################################


class pensions_alimentaires_versees(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Pensions alimentaires versées"
    reference = u"http://vosdroits.service-public.fr/particuliers/F2.xhtml"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        f6gi = foyer_fiscal('f6gi', period)
        f6gj = foyer_fiscal('f6gj', period)
        f6el = foyer_fiscal('f6el', period)
        f6em = foyer_fiscal('f6em', period)
        f6gp = foyer_fiscal('f6gp', period)
        f6gu = foyer_fiscal('f6gu', period)

        return -(f6gi + f6gj + f6el + f6em + f6gp + f6gu)


class rfr(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu fiscal de référence"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Revenu fiscal de référence
        f3vg -> rev_cat_pv -> ... -> rni
        '''
        rni = foyer_fiscal('rni', period)
        f3va_i = foyer_fiscal.members('f3va', period)
        f3vi_i = foyer_fiscal.members('f3vi', period)
        rfr_cd = foyer_fiscal('rfr_cd', period)
        rfr_rvcm = foyer_fiscal('rfr_rvcm', period)
        rpns_exon_i = foyer_fiscal.members('rpns_exon', period)
        rpns_pvce_i = foyer_fiscal.members('rpns_pvce', period)
        rev_cap_lib = foyer_fiscal('rev_cap_lib', period, options = [ADD])
        f3vz = foyer_fiscal('f3vz', period)
        microentreprise = foyer_fiscal('microentreprise', period)

        f3va = foyer_fiscal.sum(f3va_i)
        f3vi = foyer_fiscal.sum(f3vi_i)
        rpns_exon = foyer_fiscal.sum(rpns_exon_i)
        rpns_pvce = foyer_fiscal.sum(rpns_pvce_i)
        return (max_(0, rni) + rfr_cd + rfr_rvcm + rev_cap_lib + f3vi + rpns_exon + rpns_pvce + f3va +
                f3vz + microentreprise)


class glo(Variable):
    column = FloatCol
    entity = Individu
    label = u"Gain de levée d'options"
    reference = "http://www.officeo.fr/imposition-au-bareme-progressif-de-l-impot-sur-le-revenu-des-gains-de-levee-d-options-sur-actions-et-attributions-d-actions-gratuites"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Gains de levée d'option
        '''
        f1tv = individu('f1tv', period)
        f1tw = individu('f1tw', period)
        f1tx = individu('f1tx', period)
        f3vf = individu('f3vf', period)
        f3vi = individu('f3vi', period)
        f3vj = individu('f3vj', period)

        return f1tv + f1tw + f1tx + f3vf + f3vi + f3vj


class rev_cap_bar(Variable):
    """Revenus du capital imposés au barème

    Annuel pour les impôts mais mensuel pour la base ressource des minimas sociaux donc mensuel.
    """
    calculate_output = calculate_output_add
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenus du capital imposés au barème"
    set_input = set_input_divide_by_period
    reference = "http://fr.wikipedia.org/wiki/Revenu#Revenu_du_Capital"
    definition_period = MONTH

    def formula(foyer_fiscal, period, parameters):
        year = period.this_year
        f2dc = foyer_fiscal('f2dc', year)
        f2gr = foyer_fiscal('f2gr', year)
        f2ch = foyer_fiscal('f2ch', year)
        f2ts = foyer_fiscal('f2ts', year)
        f2go = foyer_fiscal('f2go', year)
        f2tr = foyer_fiscal('f2tr', year)
        f2fu = foyer_fiscal('f2fu', year)
        avf = foyer_fiscal('avf', year)
        f2da = foyer_fiscal('f2da', year)
        f2ee = foyer_fiscal('f2ee', year)
        finpfl = parameters(period).impot_revenu.autre.finpfl  # TODO remove ad check case
        majGO = parameters(period).impot_revenu.rvcm.majGO

        # year = period.start.year
        # if year <= 2011:
        #     return f2dc + f2gr + f2ch + f2ts + f2go + f2tr + f2fu - avf
        # elif year > 2011:
        #     return f2dc + f2gr + f2ch + f2ts + f2go + f2tr + f2fu - avf + (f2da + f2ee)
        return (f2dc + f2gr + f2ch + f2ts + f2go * majGO + f2tr + f2fu - avf + (f2da + f2ee) * finpfl) / 12


    # We add f2da an f2ee to allow for comparaison between years


class rev_cap_lib(Variable):
    '''Revenu du capital imposé au prélèvement libératoire

    Annuel pour les impôts mais mensuel pour la base ressource des minimas sociaux donc mensuel.
    '''
    calculate_output = calculate_output_add
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenu du capital imposé au prélèvement libératoire"
    set_input = set_input_divide_by_period
    reference = "http://fr.wikipedia.org/wiki/Revenu#Revenu_du_Capital"
    definition_period = MONTH

    def formula_2002_01_01(foyer_fiscal, period, parameters):
        year = period.this_year
        f2dh = foyer_fiscal('f2dh', year)
        f2ee = foyer_fiscal('f2ee', year)
        _P = parameters(period)
        finpfl = parameters(period).impot_revenu.autre.finpfl

        out = f2dh + f2ee
        return out * not_(finpfl) / 12

    # Cette formule a seulement été vérifiée jusqu'au 2015-12-31
    def formula_2008_01_01(foyer_fiscal, period, parameters):
        year = period.this_year
        f2da = foyer_fiscal('f2da', year)
        f2dh = foyer_fiscal('f2dh', year)
        f2ee = foyer_fiscal('f2ee', year)
        _P = parameters(period)
        finpfl = parameters(period).impot_revenu.autre.finpfl

        out = f2da + f2dh + f2ee
        return out * not_(finpfl) / 12


class avf(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Avoir fiscal et crédits d'impôt"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Avoir fiscal et crédits d'impôt (zavff)
        '''
        f2ab = foyer_fiscal('f2ab', period)

        return f2ab


class imp_lib(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Prelèvement libératoire sur les revenus du capital"
    reference = "http://www.impots.gouv.fr/portal/dgi/public/particuliers.impot?pageId=part_ctrb_soc&paf_dm=popup&paf_gm=content&typePage=cpr02&sfid=501&espId=1&impot=CS"
    definition_period = YEAR
    end = '2012-12-31'

    def formula_2002_01_01(foyer_fiscal, period, parameters):
        '''
        Prelèvement libératoire sur les revenus du capital
        '''
        f2dh = foyer_fiscal('f2dh', period)
        f2ee = foyer_fiscal('f2ee', period)
        _P = parameters(period)
        prelevement_liberatoire = parameters(period).impot_revenu.rvcm.prelevement_liberatoire

        out = -(prelevement_liberatoire.assvie * f2dh + prelevement_liberatoire.autre * f2ee)
        return out

    def formula_2008_01_01(foyer_fiscal, period, parameters):
        '''
        Prelèvement libératoire sur les revenus du capital
        '''
        f2da = foyer_fiscal('f2da', period)
        f2dh = foyer_fiscal('f2dh', period)
        f2ee = foyer_fiscal('f2ee', period)
        _P = parameters(period)
        finpfl = parameters(period).impot_revenu.autre.finpfl
        prelevement_liberatoire = parameters(period).impot_revenu.rvcm.prelevement_liberatoire

        out = -(prelevement_liberatoire.action * f2da + prelevement_liberatoire.autre * f2ee) * not_(finpfl) \
            - prelevement_liberatoire.assvie * f2dh
        return out


class fon(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Revenus fonciers"
    reference = "http://impotsurlerevenu.org/definitions/220-revenu-foncier.php"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Revenus fonciers
        '''
        f4ba = foyer_fiscal('f4ba', period)
        f4bb = foyer_fiscal('f4bb', period)
        f4bc = foyer_fiscal('f4bc', period)
        f4bd = foyer_fiscal('f4bd', period)
        f4be = foyer_fiscal('f4be', period)
        microfoncier = parameters(period).impot_revenu.rpns.micro.microfoncier

        return f4ba - f4bb - f4bc + round_(f4be * (1 - microfoncier.taux))


class rpns_pvce(Variable):
    column = FloatCol
    entity = Individu
    label = u"Plus values de cession - Revenu des professions non salariées"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Plus values de cession
        'ind'
        frag_pvce (f5hx, f5ix, f5jx)
        arag_pvce (f5he, f5ie, f5je)
        mbic_pvce (f5kq, f5lq, f5mq)
        abic_pvce (f5ke, f5le, f5me)
        macc_pvce (f5nq, f5oq, f5pq)
        aacc_pvce (f5ne, f5oe, f5pe)
        mncn_pvce (f5kv, f5lv, f5mv)
        cncn_pvce (f5so, f5nt, f5ot)
        mbnc_pvce (f5hr, f5ir, f5jr)
        abnc_pvce (f5qd, f5rd, f5sd)
        '''
        frag_pvce = individu('frag_pvce', period)
        arag_pvce = individu('arag_pvce', period)
        mbic_pvce = individu('mbic_pvce', period)
        abic_pvce = individu('abic_pvce', period)
        macc_pvce = individu('macc_pvce', period)
        aacc_pvce = individu('aacc_pvce', period)
        mbnc_pvce = individu('mbnc_pvce', period)
        abnc_pvce = individu('abnc_pvce', period)
        mncn_pvce = individu('mncn_pvce', period)
        cncn_pvce = individu('cncn_pvce', period)

        return (frag_pvce + arag_pvce + mbic_pvce + abic_pvce + macc_pvce + aacc_pvce + mbnc_pvce +
                abnc_pvce + mncn_pvce + cncn_pvce)


class rpns_exon(Variable):
    column = FloatCol
    entity = Individu
    label = u"Plus values de cession exonérées -Revenu des professions non salariées"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Plus values de cession
        'ind'
        frag_exon (f5hn, f5in, f5jn)
        arag_exon (f5hb, f5ib, f5jb)
        nrag_exon (f5hh, f5ih, f5jh)
        mbic_exon (f5kn, f5ln, f5mn)
        abic_exon (f5kb, f5lb, f5mb)
        nbic_exon (f5kh, f5lh, f5mh)
        macc_exon (f5nn, f5on, f5pn)
        aacc_exon (f5nb, f5ob, f5pb)
        nacc_exon (f5nh, f5oh, f5ph)
        mbnc_exon (f5hp, f5ip, f5jp)
        abnc_exon (f5qb, f5rb, f5sb)
        nbnc_exon (f5qh, f5rh, f5sh)
        nbnc_pvce (f5qj, f5rj, f5sj)
        '''
        frag_exon = individu('frag_exon', period)
        arag_exon = individu('arag_exon', period)
        nrag_exon = individu('nrag_exon', period)
        mbic_exon = individu('mbic_exon', period)
        abic_exon = individu('abic_exon', period)
        nbnc_proc = individu('nbnc_proc', period)
        nbic_exon = individu('nbic_exon', period)
        macc_exon = individu('macc_exon', period)
        aacc_exon = individu('aacc_exon', period)
        nacc_exon = individu('nacc_exon', period)
        mbnc_exon = individu('mbnc_exon', period)
        abnc_proc = individu('abnc_proc', period)
        nrag_pvce = individu('nrag_pvce', period)
        abnc_exon = individu('abnc_exon', period)
        nbnc_exon = individu('nbnc_exon', period)
        mncn_exon = individu('mncn_exon', period)
        cncn_exon = individu('cncn_exon', period)
        cncn_jcre = individu('cncn_jcre', period)
        cncn_info = individu('cncn_info', period)
        nbic_pvce = individu('nbic_pvce', period)
        cga = parameters(period).impot_revenu.rpns.cga_taux2

        return (frag_exon + arag_exon + nrag_exon + mbic_exon + abic_exon + nbnc_proc * (1 + cga) +
                nbic_exon + macc_exon + aacc_exon + nacc_exon + mbnc_exon + abnc_proc +
                abnc_exon + nbnc_exon + mncn_exon + cncn_exon + cncn_jcre + cncn_info + nbic_pvce + nrag_pvce)


class defrag(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Déficit agricole des années antérieures"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        f5qf = foyer_fiscal('f5qf', period)
        f5qg = foyer_fiscal('f5qg', period)
        f5qn = foyer_fiscal('f5qn', period)
        f5qo = foyer_fiscal('f5qo', period)
        f5qp = foyer_fiscal('f5qp', period)
        f5qq = foyer_fiscal('f5qq', period)
        frag_impo_i = foyer_fiscal.members('frag_impo', period)
        nrag_impg_i = foyer_fiscal.members('nrag_impg', period)
        frag_fore_i = foyer_fiscal.members('frag_fore', period)
        frag_pvct_i = foyer_fiscal.members('frag_pvct', period)
        arag_impg_i = foyer_fiscal.members('arag_impg', period)
        cga = parameters(period).impot_revenu.rpns.cga_taux2

        frag_fore = foyer_fiscal.sum(frag_fore_i)
        frag_impo = foyer_fiscal.sum(frag_impo_i)
        arag_impg = foyer_fiscal.sum(arag_impg_i)
        nrag_impg = foyer_fiscal.sum(nrag_impg_i)
        frag_pvct = foyer_fiscal.sum(frag_pvct_i)
        return min_(f5qf + f5qg + f5qn + f5qo + f5qp + f5qq, (1 + cga) * (frag_impo + nrag_impg + frag_pvct)
                    + arag_impg + frag_fore)


class defacc(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Déficit industriels et commerciaux non professionnels des années antérieures"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        f5rn = foyer_fiscal('f5rn', period)
        f5ro = foyer_fiscal('f5ro', period)
        f5rp = foyer_fiscal('f5rp', period)
        f5rq = foyer_fiscal('f5rq', period)
        f5rr = foyer_fiscal('f5rr', period)
        f5rw = foyer_fiscal('f5rw', period)
        macc_impv_i = foyer_fiscal.members('macc_impv', period)
        macc_imps_i = foyer_fiscal.members('macc_imps', period)
        nacc_impn_i = foyer_fiscal.members('nacc_impn', period)
        macc_pvct_i = foyer_fiscal.members('macc_pvct', period)
        aacc_impn_i = foyer_fiscal.members('aacc_impn', period)
        cga = parameters(period).impot_revenu.rpns.cga_taux2
        micro = parameters(period).impot_revenu.rpns.micro

        def abat_rpns(rev, P):
            return max_(0, rev - min_(rev, max_(P.taux * min_(P.max, rev), P.min)))

        nacc_impn = foyer_fiscal.sum(nacc_impn_i)
        macc_pvct = foyer_fiscal.sum(macc_pvct_i)
        macc_impv = foyer_fiscal.sum(macc_impv_i)
        macc_imps = foyer_fiscal.sum(macc_imps_i)
        aacc_impn = foyer_fiscal.sum(aacc_impn_i)
        macc_timp = abat_rpns(macc_impv, micro.specialbnc.marchandises) + abat_rpns(macc_imps, micro.specialbnc.services)
        return (
            min_(f5rn + f5ro + f5rp + f5rq + f5rr + f5rw, aacc_impn + macc_pvct + macc_timp + (1 + cga) * nacc_impn)
            )


class defncn(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Déficit non commerciaux non professionnels des années antérieures"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        f5ht = foyer_fiscal('f5ht', period)
        f5it = foyer_fiscal('f5it', period)
        f5jt = foyer_fiscal('f5jt', period)
        f5kt = foyer_fiscal('f5kt', period)
        f5lt = foyer_fiscal('f5lt', period)
        f5mt = foyer_fiscal('f5mt', period)
        mncn_impo_i = foyer_fiscal.members('mncn_impo', period)
        mncn_pvct_i = foyer_fiscal.members('mncn_pvct', period)
        cncn_aimp_i = foyer_fiscal.members('cncn_aimp', period)
        cncn_bene_i = foyer_fiscal.members('cncn_bene', period)
        cga = parameters(period).impot_revenu.rpns.cga_taux2
        specialbnc = parameters(period).impot_revenu.rpns.micro.specialbnc

        def abat_rpns(rev, P):
            return max_(0, rev - min_(rev, max_(P.taux * min_(P.max, rev), P.min)))
        cncn_bene = foyer_fiscal.sum(cncn_bene_i)
        mncn_impo = foyer_fiscal.sum(mncn_impo_i)
        mncn_pvct = foyer_fiscal.sum(mncn_pvct_i)
        cncn_aimp = foyer_fiscal.sum(cncn_aimp_i)
        return min_(
            f5ht + f5it + f5jt + f5kt + f5lt + f5mt,
            abat_rpns(mncn_impo, specialbnc.services) + mncn_pvct + cncn_aimp + (1 + cga) * cncn_bene
            )  # TODO check !


class defmeu(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Déficit des locations meublées non professionnelles des années antérieures"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        f5ga = foyer_fiscal('f5ga', period)
        f5gb = foyer_fiscal('f5gb', period)
        f5gc = foyer_fiscal('f5gc', period)
        f5gd = foyer_fiscal('f5gd', period)
        f5ge = foyer_fiscal('f5ge', period)
        f5gf = foyer_fiscal('f5gf', period)
        f5gg = foyer_fiscal('f5gg', period)
        f5gh = foyer_fiscal('f5gh', period)
        f5gi = foyer_fiscal('f5gi', period)
        f5gj = foyer_fiscal('f5gj', period)
        alnp_imps_i = foyer_fiscal.members('alnp_imps', period)
        nacc_defs_i = foyer_fiscal.members('nacc_defs', period)

        nacc_defs = foyer_fiscal.sum(nacc_defs_i)
        alnp_imps = foyer_fiscal.sum(alnp_imps_i)
        return min_(f5ga + f5gb + f5gc + f5gd + f5ge + f5gf + f5gg + f5gh + f5gi + f5gj, alnp_imps + nacc_defs)


class rag(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenus agricoles"
    reference = "http://www.impots.gouv.fr/portal/dgi/public/professionnels.impot?espId=2&impot=BA&pageId=prof_ba&sfid=50"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Revenus agricoles
        'ind'
        frag_exon (f5hn, f5in, f5jn)
        frag_impo (f5ho, f5io, f5jo)
        arag_exon (f5hb, f5ib, f5jb)
        arag_impg (f5hc, f5ic, f5jc)
        arag_defi (f5hf, f5if, f5jf)
        nrag_exon (f5hh, f5ih, f5jh)
        nrag_impg (f5hi, f5ii, f5ji)
        nrag_defi (f5hl, f5il, f5jl)
        nrag_ajag (f5hm, f5im, f5jm)
        '''
        frag_exon = individu('frag_exon', period)
        frag_impo = individu('frag_impo', period)
        arag_exon = individu('arag_exon', period)
        arag_impg = individu('arag_impg', period)
        arag_defi = individu('arag_defi', period)
        nrag_exon = individu('nrag_exon', period)
        nrag_impg = individu('nrag_impg', period)
        nrag_defi = individu('nrag_defi', period)
        nrag_ajag = individu('nrag_ajag', period)

        return (frag_exon + frag_impo +
                arag_exon + arag_impg - arag_defi +
                nrag_exon + nrag_impg - nrag_defi +
                nrag_ajag)


class ric(Variable):
    column = FloatCol
    entity = Individu
    label = u"Bénéfices industriels et commerciaux"
    reference = "http://www.impots.gouv.fr/portal/dgi/public/professionnels.impot?pageId=prof_bic&espId=2&impot=BIC&sfid=50"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Bénéfices industriels et commerciaux
        'ind'
        mbic_exon (f5kn, f5ln, f5mn)
        abic_exon (f5kb, f5lb, f5mb)
        nbic_exon (f5kh, f5lh, f5mh)
        mbic_impv (f5ko, f5lo, f5mo)
        mbic_imps (f5kp, f5lp, f5mp)
        abic_impn (f5kc, f5lc, f5mc)
        abic_imps (f5kd, f5ld, f5md)
        nbic_impn (f5ki, f5li, f5mi)
        nbic_imps (f5kj, f5lj, f5mj)
        abic_defn (f5kf, f5lf, f5mf)
        abic_defs (f5kg, f5lg, f5mg)
        nbic_defn (f5kl, f5ll, f5ml)
        nbic_defs (f5km, f5lm, f5mm)
        nbic_apch (f5ks, f5ls, f5ms)
        '''
        mbic_exon = individu('mbic_exon', period)
        mbic_impv = individu('mbic_impv', period)
        mbic_imps = individu('mbic_imps', period)
        abic_exon = individu('abic_exon', period)
        nbic_exon = individu('nbic_exon', period)
        abic_impn = individu('abic_impn', period)
        nbic_impn = individu('nbic_impn', period)
        abic_imps = individu('abic_imps', period)
        nbic_imps = individu('nbic_imps', period)
        abic_defn = individu('abic_defn', period)
        nbic_defn = individu('nbic_defn', period)
        abic_defs = individu('abic_defs', period)
        nbic_defs = individu('nbic_defs', period)
        nbic_apch = individu('nbic_apch', period)
        micro = parameters(period).impot_revenu.rpns.micro

        zbic = (
            mbic_exon + mbic_impv + mbic_imps +
            abic_exon + nbic_exon +
            abic_impn + nbic_impn +
            abic_imps + nbic_imps +
            abic_defn - nbic_defn +
            abic_defs - nbic_defs +
            nbic_apch)

        cond = (mbic_impv > 0) & (mbic_imps == 0)
        taux = micro.specialbnc.marchandises.taux * cond + micro.specialbnc.services.taux * not_(cond)

        cbic = min_(
            mbic_impv + mbic_imps + mbic_exon,
            max_(
                micro.specialbnc.marchandises.min,
                round_(
                    mbic_impv * micro.specialbnc.marchandises.taux + mbic_imps * micro.specialbnc.services.taux + mbic_exon * taux
                    )
                )
            )
        return zbic - cbic


class rac(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenus accessoires individuels"
    reference = "http://vosdroits.service-public.fr/particuliers/F1225.xhtml"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Revenus accessoires individuels
        'ind'
        macc_exon (f5nn, f5on, f5pn)
        aacc_exon (f5nb, f5ob, f5pb)
        nacc_exon (f5nh, f5oh, f5ph)
        macc_impv (f5no, f5oo, f5po)
        macc_imps (f5np, f5op, f5pp)
        aacc_impn (f5nc, f5oc, f5pc)
        aacc_imps (f5nd, f5od, f5pd)
        aacc_defn (f5nf, f5of, f5pf)
        aacc_defs (f5ng, f5og, f5pg)
        nacc_impn (f5ni, f5oi, f5pi)
        nacc_defn (f5nl, f5ol, f5pl)
        nacc_defs (f5nm, f5om, f5pm)
        mncn_impo (f5ku, f5lu, f5mu)
        cncn_bene (f5sn, f5ns, f5os)
        cncn_defi (f5sp, f5nu, f5ou, f5sr)
        f5sv????
        '''
        macc_exon = individu('macc_exon', period)
        macc_impv = individu('macc_impv', period)
        macc_imps = individu('macc_imps', period)
        aacc_exon = individu('aacc_exon', period)
        aacc_impn = individu('aacc_impn', period)
        aacc_imps = individu('aacc_imps', period)
        aacc_defn = individu('aacc_defn', period)
        aacc_defs = individu('aacc_defs', period)
        nacc_exon = individu('nacc_exon', period)
        nacc_impn = individu('nacc_impn', period)
        nacc_defn = individu('nacc_defn', period)
        nacc_defs = individu('nacc_defs', period)
        mncn_impo = individu('mncn_impo', period)
        cncn_bene = individu('cncn_bene', period)
        cncn_defi = individu('cncn_defi', period)
        micro = parameters(period).impot_revenu.rpns.micro

        zacc = (macc_exon + macc_impv + macc_imps
                + aacc_exon + aacc_impn + aacc_imps - aacc_defn - aacc_defs
                + nacc_exon + nacc_impn - nacc_defn - nacc_defs
                + mncn_impo + cncn_bene - cncn_defi)
    #TODO: aacc_imps aacc_defs
        cond = (macc_impv > 0) & (macc_imps == 0)
        taux = micro.specialbnc.marchandises.taux * cond + micro.specialbnc.services.taux * not_(cond)

        cacc = min_(macc_impv + macc_imps + macc_exon + mncn_impo, max_(micro.specialbnc.marchandises.min, round_(
            macc_impv * micro.specialbnc.marchandises.taux
            + macc_imps * micro.specialbnc.services.taux + macc_exon * taux
            + mncn_impo * micro.specialbnc.taux)))

        return zacc - cacc


class rnc(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenus non commerciaux individuels"
    reference = "http://www.impots.gouv.fr/portal/dgi/public/professionnels.impot?espId=2&pageId=prof_bnc&impot=BNC&sfid=50"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Revenus non commerciaux individuels
        'ind'
        mbnc_exon (f5hp, f5ip, f5jp)
        abnc_exon (f5qb, f5rb, f5sb)
        nbnc_exon (f5qh, f5rh, f5sh)
        mbnc_impo (f5hq, f5iq, f5jq)
        abnc_impo (f5qc, f5rc, f5sc)
        abnc_defi (f5qe, f5re, f5se)
        nbnc_impo (f5qi, f5ri, f5si)
        nbnc_defi (f5qk, f5rk, f5sk)
        f5ql, f5qm????
        '''
        mbnc_exon = individu('mbnc_exon', period)
        mbnc_impo = individu('mbnc_impo', period)
        abnc_exon = individu('abnc_exon', period)
        nbnc_exon = individu('nbnc_exon', period)
        abnc_impo = individu('abnc_impo', period)
        nbnc_impo = individu('nbnc_impo', period)
        abnc_defi = individu('abnc_defi', period)
        nbnc_defi = individu('nbnc_defi', period)
        specialbnc = parameters(period).impot_revenu.rpns.micro.specialbnc

        zbnc = (
            mbnc_exon + mbnc_impo +
            abnc_exon + nbnc_exon +
            abnc_impo + nbnc_impo - abnc_defi - nbnc_defi
            )

        cbnc = min_(
            mbnc_exon + mbnc_impo,
            max_(
                specialbnc.services.min,
                round_((mbnc_exon + mbnc_impo) * specialbnc.taux)
                )
            )

        return zbnc - cbnc


class rpns(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenus individuels des professions non salariées"
    definition_period = YEAR

    def formula(individu, period, parameters):
        rag = individu('rag', period)
        ric = individu('ric', period)
        rac = individu('rac', period)
        rnc = individu('rnc', period)

        return rag + ric + rac + rnc


class rpns_pvct(Variable):
    column = FloatCol
    entity = Individu
    label = u"Plus values de court terme -Revenu des professions non salariées"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Plus values de court terme
        'ind'
        frag_pvct (f5hw, f5iw, f5jw)
        mbic_pvct (f5kx, f5lx, f5mx)
        macc_pvct (f5nx, f5ox, f5px)
        mbnc_pvct (f5hv, f5iv, f5jv)
        mncn_pvct (f5ky, f5ly, f5my)
        '''
        frag_pvct = individu('frag_pvct', period)
        mbic_pvct = individu('mbic_pvct', period)
        macc_pvct = individu('macc_pvct', period)
        mbnc_pvct = individu('mbnc_pvct', period)
        mncn_pvct = individu('mncn_pvct', period)

        return frag_pvct + macc_pvct + mbic_pvct + mbnc_pvct + mncn_pvct


class rpns_mvct(Variable):
    column = FloatCol
    entity = Individu
    label = u"Moins values de court terme - Revenu des professions non salariées"
    definition_period = YEAR

    def formula(individu, period, parameters):
        """Moins values de court terme

        'ind'
        macc_mvct (f5iu)
        mncn_mvct (f5ju)
        mbnc_mvct (f5kz)
        """
        mbnc_mvct = individu('mbnc_mvct', period)
        macc_mvct = individu.foyer_fiscal('macc_mvct', period) * individu.has_role(FoyerFiscal.DECLARANT_PRINCIPAL)
        mncn_mvct = individu.foyer_fiscal('mncn_mvct', period) * individu.has_role(FoyerFiscal.DECLARANT_PRINCIPAL)

        return mbnc_mvct + macc_mvct  # mncn_mvct ?


class rpns_mvlt(Variable):
    column = FloatCol
    entity = Individu
    label = u"Moins values de long terme - Revenu des professions non salariées"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Moins values de long terme
        'ind'
        mbic_mvlt (f5kr, f5lr, f5mr)
        macc_mvlt (f5nr, f5or, f5pr)
        mncn_mvlt (f5kw, f5lw, f5mw)
        mbnc_mvlt (f5hs, f5is, f5js)
        '''
        mbic_mvlt = individu('mbic_mvlt', period)
        macc_mvlt = individu('macc_mvlt', period)
        mbnc_mvlt = individu('mbnc_mvlt', period)
        mncn_mvlt = individu('mncn_mvlt', period)

        return mbic_mvlt + macc_mvlt + mbnc_mvlt + mncn_mvlt


class rpns_individu(Variable):
    column = FloatCol
    entity = Individu
    label = u"Revenus des professions non salariées individuels"
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Revenus des professions non salariées individuels
        '''
        frag_impo = individu('frag_impo', period)
        arag_impg = individu('arag_impg', period)
        nrag_impg = individu('nrag_impg', period)
        arag_defi = individu('arag_defi', period)
        nrag_defi = individu('nrag_defi', period)
        mbic_impv = individu('mbic_impv', period)
        mbic_imps = individu('mbic_imps', period)
        abic_impn = individu('abic_impn', period)
        abic_imps = individu('abic_imps', period)
        abic_defn = individu('abic_defn', period)
        abic_defs = individu('abic_defs', period)
        nbic_impn = individu('nbic_impn', period)
        nbic_imps = individu('nbic_imps', period)
        nbic_defn = individu('nbic_defn', period)
        nbic_defs = individu('nbic_defs', period)
        macc_impv = individu('macc_impv', period)
        macc_imps = individu('macc_imps', period)
        nbic_mvct = individu('nbic_mvct', period)
        aacc_impn = individu('aacc_impn', period)
        aacc_defn = individu('aacc_defn', period)
        aacc_gits = individu('aacc_gits', period)
        nacc_impn = individu('nacc_impn', period)
        nacc_defn = individu('nacc_defn', period)
        nacc_defs = individu('nacc_defs', period)
        aacc_imps = individu('aacc_imps', period)
        mbnc_impo = individu('mbnc_impo', period)
        nacc_meup = individu('nacc_meup', period)
        abic_impm = individu('abic_impm', period)
        abic_defm = individu('abic_defm', period)
        abnc_impo = individu('abnc_impo', period)
        abnc_defi = individu('abnc_defi', period)
        nbic_impm = individu('nbic_impm', period)
        alnp_imps = individu('alnp_imps', period)
        nbnc_impo = individu('nbnc_impo', period)
        nbnc_defi = individu('nbnc_defi', period)
        alnp_defs = individu('alnp_defs', period)
        cbnc_assc = individu('cbnc_assc', period)
        mncn_impo = individu('mncn_impo', period)
        cncn_bene = individu('cncn_bene', period)
        cncn_defi = individu('cncn_defi', period)
        abnc_proc = individu('abnc_proc', period)
        rpns_pvct = individu('rpns_pvct', period)
        rpns_mvct = individu('rpns_mvct', period)
        nbnc_proc = individu('nbnc_proc', period)
        frag_fore = individu('frag_fore', period)
        f5sq = individu('f5sq', period)
        mncn_exon = individu('mncn_exon', period)
        cncn_exon = individu('cncn_exon', period)
        cncn_aimp = individu('cncn_aimp', period)
        cncn_adef = individu('cncn_adef', period)
        cncn_info = individu('cncn_info', period)
        cncn_jcre = individu('cncn_jcre', period)
        revimpres = individu('revimpres', period)
        pveximpres = individu('pveximpres', period)
        pvtaimpres = individu('pvtaimpres', period)
        cga_taux2 = parameters(period).impot_revenu.rpns.cga_taux2
        micro = parameters(period).impot_revenu.rpns.micro

        def abat_rpns(rev, P):
            return max_(0, rev - min_(rev, max_(P.taux * min_(P.max, rev), P.min)))

        # Jeunes agriculteurs montant de l'abattement de 50% ou 100%
        # nrag_ajag = f5hm + f5im + f5jm

    #    # déficits agricole des années antérieurs (imputables uniquement
    #    # sur des revenus agricoles)
    #    rag_timp = frag_impo + frag_pvct + arag_impg + nrag_impg
    #    cond = (AUTRE <= microentreprise.def_agri_seuil)
    #    def_agri = cond*(arag_defi + nrag_defi) + not_(cond)*min_(rag_timp, arag_defi + nrag_defi)
    #    # TODO : check 2006 cf art 156 du CGI pour 2006
    #    def_agri_ant    = min_(max_(0,rag_timp - def_agri), f5sq)

        def_agri = f5sq + arag_defi + nrag_defi

        # # B revenus industriels et commerciaux professionnels
        # regime micro entreprise
        mbic_timp = abat_rpns(mbic_impv, micro.specialbnc.marchandises) + abat_rpns(mbic_imps, micro.specialbnc.services)

        # Régime du bénéfice réel bénéficiant de l'abattement CGA
        abic_timp = abic_impn + abic_imps - (abic_defn + abic_defs)

        # Régime du bénéfice réel ne bénéficiant pas de l'abattement CGA
        nbic_timp = (nbic_impn + nbic_imps) - (nbic_defn + nbic_defs)

        # Abatemment artisant pécheur
        # nbic_apch = f5ks + f5ls + f5ms # TODO : à intégrer qqpart

        # # C revenus industriels et commerciaux non professionnels
        # (revenus accesoires du foyers en nomenclature INSEE)

        # regime micro entreprise
        macc_timp = abat_rpns(macc_impv, micro.specialbnc.marchandises) + abat_rpns(macc_imps, micro.specialbnc.services)
        # Régime du bénéfice réel bénéficiant de l'abattement CGA
        aacc_timp = (
            max_(
                0,
                (aacc_impn + (aacc_gits > 0) * max_(
                    micro.specialbnc.services.min,
                    aacc_gits * (1 - micro.specialbnc.marchandises.taux)
                    )) +
                (aacc_imps > 0) * max_(
                    micro.specialbnc.marchandises.min,
                    aacc_imps * (1 - micro.specialbnc.services.taux)
                    ) +
                (nacc_meup > 0) * max_(
                    micro.specialbnc.services.min,
                    nacc_meup * (1 - micro.specialbnc.marchandises.taux)
                    ) +
                nacc_defs - aacc_defn
                )
            )
        # Régime du bénéfice réel ne bénéficiant pas de l'abattement CGA
        nacc_timp = max_(0, nacc_impn - nacc_defn)

        # # E revenus non commerciaux non professionnels
        # regime déclaratif special ou micro-bnc
        mncn_timp = abat_rpns(mncn_impo, micro.specialbnc.services)  # TODO check

        # régime de la déclaration controlée
        # total 11
        cncn_timp = max_(0, cncn_bene - cncn_defi)
        # Abatement jeunes créateurs

        # # D revenus non commerciaux professionnels
        # regime déclaratif special ou micro-bnc
        mbnc_timp = abat_rpns(mbnc_impo, micro.specialbnc.services)  # TODO check

        # regime de la déclaration contrôlée bénéficiant de l'abattement association agréée
        abnc_timp = abnc_impo - abnc_defi

        # regime de la déclaration contrôlée ne bénéficiant pas de l'abattement association agréée
        nbnc_timp = nbnc_impo - nbnc_defi

        # # Totaux
        atimp = arag_impg + abic_timp + aacc_timp + abnc_timp
        ntimp = nrag_impg + nbic_timp + nacc_timp + nbnc_timp + cncn_timp

        majo_cga = max_(0, cga_taux2 * (ntimp + frag_impo))  # Pour ne pas avoir à majorer les déficits
        # total 6
        rev_NS = frag_impo + frag_fore + atimp + ntimp + majo_cga - def_agri

        # revenu net après abatement
        # total 7
        rev_NS_mi = mbic_timp + max_(0, macc_timp) + mbnc_timp + mncn_timp
        exon = max_(0, macc_timp + nacc_timp - rpns_mvct) - macc_timp - nacc_timp  # ajout artificiel
        RPNS = (rev_NS + rev_NS_mi + rpns_pvct + exon + abic_impm - abic_defm + alnp_imps + cncn_aimp - nbic_mvct)
        return RPNS


class abat_spe(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Abattements spéciaux"
    reference = "http://bofip.impots.gouv.fr/bofip/2036-PGP"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        """
        Abattements spéciaux

        - pour personnes âges ou invalides : âgé(e) de plus de 65 ans
          ou invalide (titulaire d’une pension d’invalidité militaire ou d’accident
          du travail d’au moins 40 % ou titulaire de la carte d’invalidité),
          abattement de 2 172 € si rng du foyer fiscal inférieur à 13 370 €
                        1 086 € si rng  compris entre 13 370 € et 21 570 €.
          Abattement doublé si conjoint remplit également ces conditions
          d’âge ou d’invalidité.
        - pour enfants à charge ayant fondé un foyer distinct : Si  rattachement
          enfants mariés ou pacsés ou enfants  célibataires, veufs, divorcés, séparés, chargés de famille,
          abattement 5 495 € par personne ainsi rattachée.
          Si l’enfant de la personne rattachée est réputé à charge de
          l’un et l’autre de ses parents (garde alternée), cet abattement est divisé
          par deux soit 2 748€. Exemple : 10 990 € pour un jeune ménage et 8 243 €
          pour un célibataire avec un jeune enfant en résidence alternée.
        """
        caseP = foyer_fiscal('caseP', period)
        caseF = foyer_fiscal('caseF', period)
        rng = foyer_fiscal('rng', period)
        nbN = foyer_fiscal('nbN', period)

        abattements_rni = parameters(period).impot_revenu.abattements_rni
        abattements_personne_agee_ou_invalide = abattements_rni.personne_agee_ou_invalide

        ageV = foyer_fiscal.declarant_principal('age', period.first_month)
        ageC = foyer_fiscal.conjoint('age', period.first_month)

        invV, invC = caseP, caseF
        nb_elig_as = (1 * (((ageV >= 65) | invV) & (ageV > 0)) +
                      1 * (((ageC >= 65) | invC) & (ageC > 0))
                      )
        as_inv = nb_elig_as * abattements_personne_agee_ou_invalide.montant * (
            (rng <= abattements_personne_agee_ou_invalide.plafond_de_ressources_1) +
            ((rng > abattements_personne_agee_ou_invalide.plafond_de_ressources_1) &
                (rng <= abattements_personne_agee_ou_invalide.plafond_de_ressources_2)
                ) * 0.5
            )

        as_enf = nbN * abattements_rni.enfant_marie.montant

        return min_(rng, as_inv + as_enf)


class taux_effectif(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"taux_effectif"
    definition_period = YEAR

    def formula_2009_01_01(foyer_fiscal, period, parameters):
        rni = foyer_fiscal('rni', period)
        nbptr = foyer_fiscal('nbptr', period)
        microentreprise = foyer_fiscal('microentreprise', period)
        abnc_proc_i = foyer_fiscal.members('abnc_proc', period)
        nbnc_proc_i = foyer_fiscal.members('nbnc_proc', period)
        bareme = parameters(period).impot_revenu.bareme
        cga = parameters(period).impot_revenu.rpns.cga_taux2
        abnc_proc = foyer_fiscal.sum(abnc_proc_i)
        nbnc_proc = foyer_fiscal.sum(nbnc_proc_i)
        base_fictive = rni + microentreprise + abnc_proc + nbnc_proc * (1 + cga)
        trigger = (microentreprise != 0) | (abnc_proc != 0) | (nbnc_proc != 0)
        return trigger * nbptr * bareme.calc(base_fictive / nbptr) / max_(1, base_fictive)


class taux_moyen_imposition(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Taux moyen d'imposition"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        rni = foyer_fiscal('rni', period)
        irpp = foyer_fiscal('irpp', period)
        return (
            (- irpp) / (rni + (rni == 0))
            ) * (rni > 0)


###############################################################################
# # Calcul du nombre de parts
###############################################################################


class nbptr(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Nombre de parts"
    reference = "http://vosdroits.service-public.fr/particuliers/F2705.xhtml"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Nombre de parts du foyer
        'foy'
        note 1 enfants et résidence alternée (formulaire 2041 GV page 10)

        quotient_familial.conj : nb part associées au conjoint d'un couple marié ou pacsé
        quotient_familial.enf1 : nb part 2 premiers enfants
        quotient_familial.enf2 : nb part enfants de rang 3 ou plus
        quotient_familial.inv1 : nb part supp enfants invalides (I, G)
        quotient_familial.inv2 : nb part supp adultes invalides (R)
        quotient_familial.not31 : nb part supp note 3 : cases W ou G pour veuf, celib ou div
        quotient_familial.not32 : nb part supp note 3 : personne seule ayant élevé des enfants
        quotient_familial.not41 : nb part supp adultes invalides (vous et/ou conjoint) note 4
        quotient_familial.not42 : nb part supp adultes anciens combattants (vous et/ou conjoint) note 4
        quotient_familial.not6 : nb part supp note 6
        quotient_familial.isol : demi-part parent isolé (T)
        quotient_familial.edcd : enfant issu du mariage avec conjoint décédé;
        '''
        nb_pac = foyer_fiscal('nb_pac', period)
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        celibataire_ou_divorce = foyer_fiscal('celibataire_ou_divorce', period)
        veuf = foyer_fiscal('veuf', period)
        jeune_veuf = foyer_fiscal('jeune_veuf', period)
        nbF = foyer_fiscal('nbF', period)
        nbG = foyer_fiscal('nbG', period)
        nbH = foyer_fiscal('nbH', period)
        nbI = foyer_fiscal('nbI', period)
        nbR = foyer_fiscal('nbR', period)
        nbJ = foyer_fiscal('nbJ', period)
        caseP = foyer_fiscal('caseP', period)
        caseW = foyer_fiscal('caseW', period)
        caseG = foyer_fiscal('caseG', period)
        caseE = foyer_fiscal('caseE', period)
        caseK = foyer_fiscal('caseK', period)
        caseN = foyer_fiscal('caseN', period)
        caseF = foyer_fiscal('caseF', period)
        caseS = foyer_fiscal('caseS', period)
        caseL = foyer_fiscal('caseL', period)
        caseT = foyer_fiscal('caseT', period.first_month)
        quotient_familial = parameters(period).impot_revenu.quotient_familial

        no_pac = nb_pac == 0  # Aucune personne à charge en garde exclusive
        has_pac = not_(no_pac)
        no_alt = nbH == 0  # Aucun enfant à charge en garde alternée
        has_alt = not_(no_alt)

        # # nombre de parts liées aux enfants à charge
        # que des enfants en résidence alternée
        enf1 = (no_pac & has_alt) * (quotient_familial.enf1 * min_(nbH, 2) * 0.5
                                     + quotient_familial.enf2 * max_(nbH - 2, 0) * 0.5)
        # pas que des enfants en résidence alternée
        enf2 = (has_pac & has_alt) * ((nb_pac == 1) * (quotient_familial.enf1 * min_(nbH, 1) * 0.5
            + quotient_familial.enf2 * max_(nbH - 1, 0) * 0.5) + (nb_pac > 1) * (quotient_familial.enf2 * nbH * 0.5))
        # pas d'enfant en résidence alternée
        enf3 = quotient_familial.enf1 * min_(nb_pac, 2) + quotient_familial.enf2 * max_((nb_pac - 2), 0)

        enf = enf1 + enf2 + enf3
        # # note 2 : nombre de parts liées aux invalides (enfant + adulte)
        n2 = quotient_familial.inv1 * (nbG + nbI / 2) + quotient_familial.inv2 * nbR

        # # note 3 : Pas de personne à charge
        # - invalide

        n31a = quotient_familial.not31a * (no_pac & no_alt & caseP)
        # - ancien combatant
        n31b = quotient_familial.not31b * (no_pac & no_alt & (caseW | caseG))
        n31 = max_(n31a, n31b)
        # - personne seule ayant élevé des enfants
        n32 = quotient_familial.not32 * (no_pac & no_alt & ((caseE | caseK) & not_(caseN)))
        n3 = max_(n31, n32)
        # # note 4 Invalidité de la personne ou du conjoint pour les mariés ou
        # # jeunes veuf(ve)s
        n4 = max_(quotient_familial.not41 * (1 * caseP + 1 * caseF), quotient_familial.not42 * (caseW | caseS))

        # # note 5
        #  - enfant du conjoint décédé
        n51 = quotient_familial.cdcd * (caseL & ((nbF + nbJ) > 0))
        #  - enfant autre et parent isolé
        n52 = quotient_familial.isol * caseT * (((no_pac & has_alt) * ((nbH == 1) * 0.5 + (nbH >= 2))) + 1 * has_pac)
        n5 = max_(n51, n52)

        # # note 6 invalide avec personne à charge
        n6 = quotient_familial.not6 * (caseP & (has_pac | has_alt))

        # # note 7 Parent isolé
        n7 = quotient_familial.isol * caseT * ((no_pac & has_alt) * ((nbH == 1) * 0.5 + (nbH >= 2)) + 1 * has_pac)

        # # Régime des mariés ou pacsés
        m = 1 + quotient_familial.conj + enf + n2 + n4

        # # veufs  hors jeune_veuf
        v = 1 + enf + n2 + n3 + n5 + n6

        # # celib div
        c = 1 + enf + n2 + n3 + n6 + n7

        return (maries_ou_pacses | jeune_veuf) * m + (veuf & not_(jeune_veuf)) * v + celibataire_ou_divorce * c


###############################################################################
# # Calcul de la prime pour l'emploi
###############################################################################


class ppe_coef(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Coefficient de conversion - Prime pour l'emploi"
    end = '2015-12-31'
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        PPE: coefficient de conversion en cas de changement en cours d'année
        '''
        jour_xyz = foyer_fiscal('jour_xyz', period)

        nb_jour = (jour_xyz == 0) + jour_xyz
        return 360 / nb_jour


class ppe_elig(Variable):
    column = BoolCol
    entity = FoyerFiscal
    label = u"PPE: eligibilité à la ppe, condition sur le revenu fiscal de référence"
    end = '2015-12-31'
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        PPE: eligibilité à la ppe, condition sur le revenu fiscal de référence
        CF ligne 1: http://bofip.impots.gouv.fr/bofip/3913-PGP.html
        '''
        rfr = foyer_fiscal('rfr', period)
        ppe_coef = foyer_fiscal('ppe_coef', period)
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        veuf = foyer_fiscal('veuf', period)
        celibataire_ou_divorce = foyer_fiscal('celibataire_ou_divorce', period)
        nbptr = foyer_fiscal('nbptr', period)
        ppe = parameters(period).impot_revenu.credits_impot.ppe

        seuil = (veuf | celibataire_ou_divorce) * (ppe.eligi1 + 2 * max_(nbptr - 1, 0) * ppe.eligi3) \
                + maries_ou_pacses * (ppe.eligi2 + 2 * max_(nbptr - 2, 0) * ppe.eligi3)
        return (rfr * ppe_coef) <= seuil


class ppe_rev(Variable):
    column = FloatCol
    entity = Individu
    label = u"Base ressource de la ppe"
    end = '2015-12-31'
    definition_period = YEAR

    def formula(individu, period, parameters):
        salaire_imposable = individu('salaire_imposable', period, options = [ADD])
        hsup = individu('hsup', period, options = [ADD])
        rpns = individu('rpns', period)
        ppe = parameters(period).impot_revenu.credits_impot.ppe

        # Revenu d'activité salarié
        rev_sa = salaire_imposable + hsup  # TODO: + TV + TW + TX + AQ + LZ + VJ
        # Revenu d'activité non salarié
        rev_ns = min_(0, rpns) / ppe.abatns + max_(0, rpns) * ppe.abatns
        # très bizarre la partie min(0, rpns) - après vérification c'est dans la loi
        return rev_sa + rev_ns


class ppe_coef_tp(Variable):
    column = FloatCol
    entity = Individu
    label = u"PPE: coefficient de conversion temps partiel"
    end = '2015-12-31'
    definition_period = YEAR

    def formula(individu, period, parameters):
        ppe_du_sa = individu('ppe_du_sa', period, options = [ADD])
        ppe_du_ns = individu('ppe_du_ns', period)
        ppe_tp_sa = individu('ppe_tp_sa', period)
        ppe_tp_ns = individu('ppe_tp_ns', period)
        ppe = parameters(period).impot_revenu.credits_impot.ppe

        frac_sa = ppe_du_sa / ppe.TP_nbh
        frac_ns = ppe_du_ns / ppe.TP_nbj
        tp = ppe_tp_sa | ppe_tp_ns | (frac_sa + frac_ns >= 1)
        return tp + not_(tp) * (frac_sa + frac_ns)


class ppe_base(Variable):
    column = FloatCol
    entity = Individu
    label = u"Montant de base de la PPE"
    end = '2015-12-31'
    definition_period = YEAR

    def formula(individu, period, parameters):
        ppe_rev = individu('ppe_rev', period)
        ppe_coef_tp = individu('ppe_coef_tp', period)
        ppe_coef = individu.foyer_fiscal('ppe_coef', period)

        return ppe_rev / (ppe_coef_tp + (ppe_coef_tp == 0)) * ppe_coef


class ppe_elig_individu(Variable):
    column = BoolCol(default = False)
    entity = Individu
    label = u"Eligibilité individuelle à la ppe"
    end = '2015-12-31'
    definition_period = YEAR

    def formula(individu, period, parameters):
        '''
        Eligibilité individuelle à la ppe
        Attention : condition de plafonnement introduite dans ppe brute
        '''
        ppe_rev = individu('ppe_rev', period)
        ppe_coef_tp = individu('ppe_coef_tp', period)
        ppe = parameters(period).impot_revenu.credits_impot.ppe

        return (ppe_rev >= ppe.seuil1) & (ppe_coef_tp != 0)


class ppe_brute(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Prime pour l'emploi brute"
    end = '2015-12-31'
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        '''
        Prime pour l'emploi (avant éventuel dispositif de cumul avec le RSA)
        Cf. http://travail-emploi.gouv.fr/informations-pratiques,89/fiches-pratiques,91/remuneration,113/la-prime-pour-l-emploi-ppe,1034.html
        '''
        ppe_elig = foyer_fiscal('ppe_elig', period)
        ppe_coef = foyer_fiscal('ppe_coef', period)
        nb_pac = foyer_fiscal('nb_pac', period)
        maries_ou_pacses = foyer_fiscal('maries_ou_pacses', period)
        celibataire_ou_divorce = foyer_fiscal('celibataire_ou_divorce', period)
        veuf = foyer_fiscal('veuf', period)
        caseT = foyer_fiscal('caseT', period.first_month)
        caseL = foyer_fiscal('caseL', period)
        nbH = foyer_fiscal('nbH', period)
        ppe = parameters(period).impot_revenu.credits_impot.ppe

        eliv = foyer_fiscal.declarant_principal('ppe_elig_individu', period)
        elic = foyer_fiscal.conjoint('ppe_elig_individu', period)
        eligible_i = foyer_fiscal.members('ppe_elig_individu', period)

        basevi = foyer_fiscal.declarant_principal('ppe_rev', period)
        baseci = foyer_fiscal.conjoint('ppe_rev', period)

        basev = foyer_fiscal.declarant_principal('ppe_base', period)
        basec = foyer_fiscal.conjoint('ppe_base', period)
        base_i = foyer_fiscal.members('ppe_base', period)

        coef_tpv = foyer_fiscal.declarant_principal('ppe_coef_tp', period)
        coef_tpc = foyer_fiscal.conjoint('ppe_coef_tp', period)
        coef_tp_i = foyer_fiscal.members('ppe_coef_tp', period)

        nb_pac_ppe = max_(0, nb_pac - foyer_fiscal.sum(eligible_i, role = FoyerFiscal.PERSONNE_A_CHARGE))

        ligne2 = maries_ou_pacses & xor_(basevi >= ppe.seuil1, baseci >= ppe.seuil1)
        ligne3 = (celibataire_ou_divorce | veuf) & caseT & not_(veuf & caseT & caseL)
        ligne1 = not_(ligne2) & not_(ligne3)

        base_monact = ligne2 * (eliv * basev + elic * basec)
        base_monacti = ligne2 * (eliv * basevi + elic * baseci)

        def ppe_bar1(base):
    #        cond1 = ligne1 | ligne3
    #        cond2 = ligne2
    #        return 1 / ppe_coef * ((cond1 & (base <= ppe.seuil2)) * (base) * ppe.taux1 +
    #                           (cond1 & (base > ppe.seuil2) & (base <= ppe.seuil3)) * (ppe.seuil3 - base) * ppe.taux2 +
    #                           (cond2 & (base <= ppe.seuil2)) * (base * ppe.taux1) +
    #                           (cond2 & (base > ppe.seuil2) & (base <= ppe.seuil3)) * ((ppe.seuil3 - base) * ppe.taux2) +
    #                           (cond2 & (base > ppe.seuil4) & (base <= ppe.seuil5)) * (ppe.seuil5 - base) * ppe.taux3)
            return (
                (base <= ppe.seuil2) * (base) * ppe.taux1 +
                (base > ppe.seuil2) * (base <= ppe.seuil3) * (ppe.seuil3 - base) * ppe.taux2 +
                ligne2 * (base > ppe.seuil4) * (base <= ppe.seuil5) * (ppe.seuil5 - base) * ppe.taux3
                )

        def ppe_bar2(base):
            return (
                (base <= ppe.seuil2) * (base) * ppe.taux1
                + ((base > ppe.seuil2) & (base <= ppe.seuil3)) * (ppe.seuil3 - base) * ppe.taux2)

        # calcul des primes individuelles.

        ppev = eliv * (1 / ppe_coef) * ppe_bar1(basev)
        ppec = elic * (1 / ppe_coef) * ppe_bar1(basec)

        # Primes de monoactivité
        ppe_monact_vous = (eliv & ligne2 & (basevi >= ppe.seuil1) & (basev <= ppe.seuil4)) * ppe.monact
        ppe_monact_conj = (elic & ligne2 & (baseci >= ppe.seuil1) & (basec <= ppe.seuil4)) * ppe.monact

        # Primes pour enfants à charge
        maj_pac = ppe_elig * (eliv | elic) * (
            (ligne1 & maries_ou_pacses & ((ppev + ppec) != 0) & (min_(basev, basec) <= ppe.seuil3)) * ppe.pac
            * (nb_pac_ppe + nbH * 0.5)
            + (ligne1 & (celibataire_ou_divorce | veuf) & eliv & (basev <= ppe.seuil3)) * ppe.pac * (nb_pac_ppe + nbH * 0.5)
            + (ligne2 & (base_monacti >= ppe.seuil1) & (base_monact <= ppe.seuil3)) * ppe.pac * (nb_pac_ppe + nbH * 0.5)
            + (ligne2 & (base_monact > ppe.seuil3) & (base_monact <= ppe.seuil5)) * ppe.pac
            * ((nb_pac_ppe != 0) + 0.5 * ((nb_pac_ppe == 0) & (nbH != 0)))
            + (ligne3 & (basevi >= ppe.seuil1) & (basev <= ppe.seuil3)) * (
                (min_(nb_pac_ppe, 1) * 2 * ppe.pac + max_(nb_pac_ppe - 1, 0) * ppe.pac)
                + (nb_pac_ppe == 0) * (min_(nbH, 2) * ppe.pac + max_(nbH - 2, 0) * ppe.pac * 0.5))
            + (ligne3 & (basev > ppe.seuil3) & (basev <= ppe.seuil5)) * ppe.pac
            * ((nb_pac_ppe != 0) * 2 + ((nb_pac_ppe == 0) & (nbH != 0))))

        def coef(coef_tp):
            return (coef_tp <= 0.5) * coef_tp * 1.45 + (coef_tp > 0.5) * (0.55 * coef_tp + 0.45)

        ppe_vous = ppe_elig * (ppev * coef(coef_tpv) + ppe_monact_vous)
        ppe_conj = ppe_elig * (ppec * coef(coef_tpc) + ppe_monact_conj)

        ppe_pac = ppe_elig * (1 / ppe_coef) * foyer_fiscal.sum(
            eligible_i * ppe_bar2(base_i) * coef(coef_tp_i),
            role = FoyerFiscal.PERSONNE_A_CHARGE)

        ppe_tot = ppe_vous + ppe_conj + ppe_pac + maj_pac

        ppe_tot = (ppe_tot != 0) * max_(ppe.versmin, ppe_tot)

        return ppe_tot


class ppe(Variable):
    column = FloatCol
    entity = FoyerFiscal
    label = u"Prime pour l'emploi"
    end = '2015-12-31'
    reference = "http://vosdroits.service-public.fr/particuliers/F2882.xhtml"
    definition_period = YEAR

    def formula(foyer_fiscal, period, parameters):
        """
        PPE effectivement versée
        """
        ppe_brute = foyer_fiscal('ppe_brute', period)

        # TODO: les foyers qui paient l'ISF n'ont pas le droit à la PPE
        rsa_act_i = foyer_fiscal.members('rsa_activite_individu', period, options = [ADD])
        rsa_act = foyer_fiscal.sum(rsa_act_i, role = FoyerFiscal.DECLARANT)

        #   On retranche le RSA activité de la PPE
        #   Dans les agrégats officiels de la DGFP, c'est à la PPE brute qu'il faut comparer
        ppe = max_(ppe_brute - rsa_act, 0)
        return ppe
