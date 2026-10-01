import Challenge
import Seeded
import Duper
import Canonical
import Bench.Harness

set_option Elab.async false
set_option maxHeartbeats 0

theorem t_root__duper : S_root := by unfold S_root; attempt "root/duper" 60 (duper [*])
#print axioms t_root__duper
theorem t_root__canonical : S_root := by unfold S_root; attempt "root/canonical" 60 (canonical 55)
#print axioms t_root__canonical

theorem t_root_set__duper : S_root_set := by unfold S_root_set; attempt "root_set/duper" 60 (duper [*])
#print axioms t_root_set__duper
theorem t_root_set__canonical : S_root_set := by unfold S_root_set; attempt "root_set/canonical" 60 (canonical 55)
#print axioms t_root_set__canonical

theorem t_prime_mod_four__duper : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/duper" 60 (duper [*])
#print axioms t_prime_mod_four__duper
theorem t_prime_mod_four__canonical : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/canonical" 60 (canonical 55)
#print axioms t_prime_mod_four__canonical

theorem t_mul_one_mod_four__duper : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/duper" 60 (duper [*])
#print axioms t_mul_one_mod_four__duper
theorem t_mul_one_mod_four__canonical : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/canonical" 60 (canonical 55)
#print axioms t_mul_one_mod_four__canonical

theorem t_factor_three_mod_four__duper : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/duper" 60 (duper [*])
#print axioms t_factor_three_mod_four__duper
theorem t_factor_three_mod_four__canonical : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/canonical" 60 (canonical 55)
#print axioms t_factor_three_mod_four__canonical

theorem t_factor_three_mod_four_bare__duper : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/duper" 60 (duper [*])
#print axioms t_factor_three_mod_four_bare__duper
theorem t_factor_three_mod_four_bare__canonical : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/canonical" 60 (canonical 55)
#print axioms t_factor_three_mod_four_bare__canonical

theorem t_euclid_mod_four__duper : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/duper" 60 (duper [*])
#print axioms t_euclid_mod_four__duper
theorem t_euclid_mod_four__canonical : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/canonical" 60 (canonical 55)
#print axioms t_euclid_mod_four__canonical

theorem t_not_dvd_euclid__duper : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/duper" 60 (duper [*])
#print axioms t_not_dvd_euclid__duper
theorem t_not_dvd_euclid__canonical : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/canonical" 60 (canonical 55)
#print axioms t_not_dvd_euclid__canonical

theorem t_dvd_factorial__duper : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/duper" 60 (duper [*])
#print axioms t_dvd_factorial__duper
theorem t_dvd_factorial__canonical : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/canonical" 60 (canonical 55)
#print axioms t_dvd_factorial__canonical

theorem t_euclid__duper : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/duper" 60 (duper [*])
#print axioms t_euclid__duper
theorem t_euclid__canonical : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/canonical" 60 (canonical 55)
#print axioms t_euclid__canonical

theorem t_set_form__duper : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/duper" 60 (duper [*])
#print axioms t_set_form__duper
theorem t_set_form__canonical : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/canonical" 60 (canonical 55)
#print axioms t_set_form__canonical

theorem t_odd_factor_three__duper : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/duper" 60 (duper [*])
#print axioms t_odd_factor_three__duper
theorem t_odd_factor_three__canonical : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/canonical" 60 (canonical 55)
#print axioms t_odd_factor_three__canonical

theorem t_euclid_mod_four_any__duper : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/duper" 60 (duper [*])
#print axioms t_euclid_mod_four_any__duper
theorem t_euclid_mod_four_any__canonical : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/canonical" 60 (canonical 55)
#print axioms t_euclid_mod_four_any__canonical

theorem t_even_three_mod_four__duper : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/duper" 60 (duper [*])
#print axioms t_even_three_mod_four__duper
theorem t_even_three_mod_four__canonical : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/canonical" 60 (canonical 55)
#print axioms t_even_three_mod_four__canonical
