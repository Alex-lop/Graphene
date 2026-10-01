import Proofs.PrimeModFour
import Proofs.MulOneModFour
import Proofs.FactorThreeModFour
import Proofs.EuclidModFour
import Proofs.NotDvdEuclid
import Proofs.DvdFactorial
import Proofs.Euclid
import Proofs.SetForm

/-! Written from the tree, not by a leaf: each leaf applied to the leaves it needs. -/

theorem root : S_root :=
  euclid (factor_three_mod_four prime_mod_four mul_one_mod_four) euclid_mod_four not_dvd_euclid
    dvd_factorial

theorem root_set : S_root_set := set_form root
