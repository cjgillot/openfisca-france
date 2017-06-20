#! -*- coding: utf-8 -*-

import openfisca_france.model.base as off
import numpy as np

class surface(off.Variable):
    column = off.FloatCol
    entity = off.Menage
    label  = u"Surface du logement"
    definition_period = off.MONTH
    set_input = off.set_input_dispatch_by_period

# Références :
# [1] CCH, Articles R351-60 et suivants.
# [2] Arrêté du 30/06/1979 relatif au calcul de l'aide
#     personnalisée au logement attribuée aux personnes
#     résidant dans un logement-foyer.

# Prelude {{{1
def conditions(couple, al_nb_pac, maxi):
    ret = [
        np.logical_not(couple) * (al_nb_pac == 0),
        couple * (al_nb_pac == 0)
    ]
    ret.extend((
        (al_nb_pac == i)
        for i in range(1, maxi)
    ))
    ret.append(al_nb_pac >= maxi)
    return ret

class scale_pac: # {{{1
    def __init__(self, valeurs, supp):
        self.V = np.array(valeurs).transpose()
        self.S = supp
    def __call__(self, couple, al_nb_pac):
        v1 = np.select(conditions(couple, al_nb_pac, 4), self.V)
        v1 += np.maximum(0, self.S * (al_nb_pac - 4))
        return v1

# N {{{1
# CCH R351-61
n_valeurs_1 = scale_pac([ 1.4, 1.8, 2.5, 3.0, 3.7, 4.3 ], 0.5)
# CCH R351-61-1
n_valeurs_2 = scale_pac([ 1.2, 1.5, 2.5, 3.0, 3.7, 4.3 ], 0.5)

class aplf1_n(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer 1 - nombre de parts"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        al_nb_pac = famille('al_nb_personnes_a_charge', period)
        couple = famille('al_couple', period)
        return n_valeurs_1(couple, al_nb_pac)

class aplf2_n(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer 2 - nombre de parts"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        al_nb_pac = famille('al_nb_personnes_a_charge', period)
        couple = famille('al_couple', period)
        return n_valeurs_2(couple, al_nb_pac)

# E {{{1
# [2] - Article 1
e_plafonds = np.array([ # Par zone APL
    np.zeros(6),
    [438.49, 514.05, 548.12, 586.59, 625.21, 674.21],
    [400.99, 467.99, 498.99, 534.14, 569.15, 606.47],
    [380.62, 442.69, 469.66, 500.65, 513.64, 566.48],
])
e_plafonds_supp = np.array([ # Par zone APL
    0.,
    69.94,
    63.21,
    58.66,
])
e_plafonds[0] = e_plafonds[1]
e_plafonds_supp[0] = e_plafonds_supp[1]

class aplf_redevance_plafond(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer - Redevance plafond"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        al_nb_pac = famille('al_nb_personnes_a_charge', period)
        couple = famille('al_couple', period)
        zone = famille.demandeur.menage('zone_apl', period)
        plafond = scale_pac(e_plafonds[zone,:],
                            e_plafonds_supp[zone])(couple, al_nb_pac)
        return plafond

class aplf_redevance(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer - Redevance"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        plafond = famille('aplf_redevance_plafond', period)
        e = famille.demandeur.menage('loyer', period)
        return np.minimum(e, plafond)

# E0 {{{1
class aplf_tranchage: # {{{
    tranches = None
    taux     = None
    supp     = None

    def __init__(self, tranches, taux, supp):
        self.tranches = tranches
        self.taux     = taux
        self.supp     = supp

    def calc(self, R, N):
        # CCH Articles R351-62 et R351-62-1
        E0 = 0 * R
        for t in range(0, self.tranches.size):
            tr_mini = self.tranches[t] * N
            tr_taux = self.taux[t+1] - self.taux[t]
            E0 += tr_taux * np.maximum(R - tr_taux, 0)
        E0 += self.supp * N
        E0 /= 12
        return E0
# }}}
# [2] - Article 4
aplf1_e0 = aplf_tranchage(
    tranches = np.array([0.,  1948.10, 2678.71, 3896.18, 5357.44, 6331.29]),
    taux = np.array([0,  .04, .104,    .216,    .264,    .32,     .48 ]),
    supp = 45.57
)
# [2] - Article 4-1
aplf2_e0 = aplf_tranchage(
    tranches = np.array([0., 1423.03, 2047.61, 2629.85, 4096.05]),
    taux = np.array([0,  0., .024,    .208,    .232,    .328]),
    supp = 76.32
)

class aplf1_redevance_seuil(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer 1 - Redevance seuil"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        R = famille('aide_logement_base_ressources', period)
        N = famille('aplf1_n', period)
        return aplf1_e0.calc(R, N)

class aplf2_redevance_seuil(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer 2 - Redevance seuil"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        R = famille('aide_logement_base_ressources', period)
        N = famille('aplf2_n', period)
        return aplf2_e0.calc(R, N)

# K {{{1
class aplf1_taux(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer 1 - Taux de prise en charge"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        # CCH R351-61
        R = famille('aide_logement_base_ressources', period)
        N = famille('aplf1_n', period)

        # [2] Article 3
        Cm = 13393.40
        r  =  1217.26

        baisse = (R - r*N)/(Cm * N)
        return 0.95 - np.maximum(baisse, 0)

class aplf2_taux(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer 2 - Taux de prise en charge"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        # CCH R351-61-1
        R = famille('aide_logement_base_ressources', period)
        N = famille('aplf2_n', period)

        # [2] Article 4-1
        Cm = 21420.91

        baisse = R/(Cm * N)
        return 0.9 - np.maximum(baisse, 0)

# Public interface {{{1
# CCH Article R351-60
# .995 correspond à la CRDS

class aplf1(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer 1"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        N = famille('aplf1_n', period)
        e = famille('aplf_redevance', period)
        e0 = famille('aplf1_redevance_seuil', period)
        k = famille('aplf1_taux', period)
        brut = k * np.maximum(e - e0, 0)
        net  = .995 * brut
        # [2] Articles 5 et 6
        net = net.clip(max = e - 26.68)
        net[net < 15.] = 0.
        return net

class aplf2(off.Variable):
    column = off.FloatCol
    entity = off.Famille
    label  = u"APL foyer 2"
    definition_period = off.MONTH

    def formula(famille, period, legislation):
        N = famille('aplf2_n', period)
        e = famille('aplf_redevance', period)
        e0 = famille('aplf2_redevance_seuil', period)
        k = famille('aplf2_taux', period)
        brut = k * np.maximum(e - e0, 0)
        net  = .995 * brut
        # [2] Articles 5 et 6
        net = net.clip(max = e - 15)
        net[net < 15.] = 0.
        return net
