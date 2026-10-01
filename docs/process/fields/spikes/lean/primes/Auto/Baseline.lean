import Challenge
import Seeded
import Auto.Harness

set_option Elab.async false
set_option maxHeartbeats 0

theorem warmup : (2 : ℕ) ∣ 4 := by attempt "warmup/exact?" 300 (exact?)

theorem t_root__decide : S_root := by unfold S_root; attempt "root/decide" 60 (decide)
#print axioms t_root__decide
theorem t_root__norm_num : S_root := by unfold S_root; attempt "root/norm_num" 60 (norm_num)
#print axioms t_root__norm_num
theorem t_root__simp : S_root := by unfold S_root; attempt "root/simp" 60 (simp)
#print axioms t_root__simp
theorem t_root__simp_all : S_root := by unfold S_root; attempt "root/simp_all" 60 (simp_all)
#print axioms t_root__simp_all
theorem t_root__omega : S_root := by unfold S_root; attempt "root/omega" 60 (omega)
#print axioms t_root__omega
theorem t_root__aesop : S_root := by unfold S_root; attempt "root/aesop" 60 (aesop)
#print axioms t_root__aesop
theorem t_root__exact_ : S_root := by unfold S_root; attempt "root/exact?" 60 (exact?)
#print axioms t_root__exact_
theorem t_root__grind : S_root := by unfold S_root; attempt "root/grind" 60 (grind)
#print axioms t_root__grind
theorem t_root__grind_suggestions : S_root := by unfold S_root; attempt "root/grind+suggestions" 60 (grind +suggestions)
#print axioms t_root__grind_suggestions
theorem t_root__try_ : S_root := by unfold S_root; attempt "root/try?" 60 (try?)
#print axioms t_root__try_

theorem t_root_set__decide : S_root_set := by unfold S_root_set; attempt "root_set/decide" 60 (decide)
#print axioms t_root_set__decide
theorem t_root_set__norm_num : S_root_set := by unfold S_root_set; attempt "root_set/norm_num" 60 (norm_num)
#print axioms t_root_set__norm_num
theorem t_root_set__simp : S_root_set := by unfold S_root_set; attempt "root_set/simp" 60 (simp)
#print axioms t_root_set__simp
theorem t_root_set__simp_all : S_root_set := by unfold S_root_set; attempt "root_set/simp_all" 60 (simp_all)
#print axioms t_root_set__simp_all
theorem t_root_set__omega : S_root_set := by unfold S_root_set; attempt "root_set/omega" 60 (omega)
#print axioms t_root_set__omega
theorem t_root_set__aesop : S_root_set := by unfold S_root_set; attempt "root_set/aesop" 60 (aesop)
#print axioms t_root_set__aesop
theorem t_root_set__exact_ : S_root_set := by unfold S_root_set; attempt "root_set/exact?" 60 (exact?)
#print axioms t_root_set__exact_
theorem t_root_set__grind : S_root_set := by unfold S_root_set; attempt "root_set/grind" 60 (grind)
#print axioms t_root_set__grind
theorem t_root_set__grind_suggestions : S_root_set := by unfold S_root_set; attempt "root_set/grind+suggestions" 60 (grind +suggestions)
#print axioms t_root_set__grind_suggestions
theorem t_root_set__try_ : S_root_set := by unfold S_root_set; attempt "root_set/try?" 60 (try?)
#print axioms t_root_set__try_

theorem t_prime_mod_four__decide : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/decide" 60 (decide)
#print axioms t_prime_mod_four__decide
theorem t_prime_mod_four__norm_num : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/norm_num" 60 (norm_num)
#print axioms t_prime_mod_four__norm_num
theorem t_prime_mod_four__simp : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/simp" 60 (simp)
#print axioms t_prime_mod_four__simp
theorem t_prime_mod_four__simp_all : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/simp_all" 60 (simp_all)
#print axioms t_prime_mod_four__simp_all
theorem t_prime_mod_four__omega : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/omega" 60 (omega)
#print axioms t_prime_mod_four__omega
theorem t_prime_mod_four__aesop : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/aesop" 60 (aesop)
#print axioms t_prime_mod_four__aesop
theorem t_prime_mod_four__exact_ : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/exact?" 60 (exact?)
#print axioms t_prime_mod_four__exact_
theorem t_prime_mod_four__grind : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/grind" 60 (grind)
#print axioms t_prime_mod_four__grind
theorem t_prime_mod_four__grind_suggestions : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/grind+suggestions" 60 (grind +suggestions)
#print axioms t_prime_mod_four__grind_suggestions
theorem t_prime_mod_four__try_ : S_prime_mod_four := by unfold S_prime_mod_four; attempt "prime_mod_four/try?" 60 (try?)
#print axioms t_prime_mod_four__try_

theorem t_mul_one_mod_four__decide : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/decide" 60 (decide)
#print axioms t_mul_one_mod_four__decide
theorem t_mul_one_mod_four__norm_num : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/norm_num" 60 (norm_num)
#print axioms t_mul_one_mod_four__norm_num
theorem t_mul_one_mod_four__simp : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/simp" 60 (simp)
#print axioms t_mul_one_mod_four__simp
theorem t_mul_one_mod_four__simp_all : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/simp_all" 60 (simp_all)
#print axioms t_mul_one_mod_four__simp_all
theorem t_mul_one_mod_four__omega : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/omega" 60 (omega)
#print axioms t_mul_one_mod_four__omega
theorem t_mul_one_mod_four__aesop : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/aesop" 60 (aesop)
#print axioms t_mul_one_mod_four__aesop
theorem t_mul_one_mod_four__exact_ : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/exact?" 60 (exact?)
#print axioms t_mul_one_mod_four__exact_
theorem t_mul_one_mod_four__grind : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/grind" 60 (grind)
#print axioms t_mul_one_mod_four__grind
theorem t_mul_one_mod_four__grind_suggestions : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/grind+suggestions" 60 (grind +suggestions)
#print axioms t_mul_one_mod_four__grind_suggestions
theorem t_mul_one_mod_four__try_ : S_mul_one_mod_four := by unfold S_mul_one_mod_four; attempt "mul_one_mod_four/try?" 60 (try?)
#print axioms t_mul_one_mod_four__try_

theorem t_factor_three_mod_four__decide : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/decide" 60 (decide)
#print axioms t_factor_three_mod_four__decide
theorem t_factor_three_mod_four__norm_num : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/norm_num" 60 (norm_num)
#print axioms t_factor_three_mod_four__norm_num
theorem t_factor_three_mod_four__simp : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/simp" 60 (simp)
#print axioms t_factor_three_mod_four__simp
theorem t_factor_three_mod_four__simp_all : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/simp_all" 60 (simp_all)
#print axioms t_factor_three_mod_four__simp_all
theorem t_factor_three_mod_four__omega : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/omega" 60 (omega)
#print axioms t_factor_three_mod_four__omega
theorem t_factor_three_mod_four__aesop : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/aesop" 60 (aesop)
#print axioms t_factor_three_mod_four__aesop
theorem t_factor_three_mod_four__exact_ : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/exact?" 60 (exact?)
#print axioms t_factor_three_mod_four__exact_
theorem t_factor_three_mod_four__grind : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/grind" 60 (grind)
#print axioms t_factor_three_mod_four__grind
theorem t_factor_three_mod_four__grind_suggestions : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/grind+suggestions" 60 (grind +suggestions)
#print axioms t_factor_three_mod_four__grind_suggestions
theorem t_factor_three_mod_four__try_ : S_prime_mod_four → S_mul_one_mod_four → S_factor_three_mod_four := by intro h0 h1; unfold S_prime_mod_four at h0; unfold S_mul_one_mod_four at h1; unfold S_factor_three_mod_four; attempt "factor_three_mod_four/try?" 60 (try?)
#print axioms t_factor_three_mod_four__try_

theorem t_factor_three_mod_four_bare__decide : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/decide" 60 (decide)
#print axioms t_factor_three_mod_four_bare__decide
theorem t_factor_three_mod_four_bare__norm_num : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/norm_num" 60 (norm_num)
#print axioms t_factor_three_mod_four_bare__norm_num
theorem t_factor_three_mod_four_bare__simp : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/simp" 60 (simp)
#print axioms t_factor_three_mod_four_bare__simp
theorem t_factor_three_mod_four_bare__simp_all : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/simp_all" 60 (simp_all)
#print axioms t_factor_three_mod_four_bare__simp_all
theorem t_factor_three_mod_four_bare__omega : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/omega" 60 (omega)
#print axioms t_factor_three_mod_four_bare__omega
theorem t_factor_three_mod_four_bare__aesop : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/aesop" 60 (aesop)
#print axioms t_factor_three_mod_four_bare__aesop
theorem t_factor_three_mod_four_bare__exact_ : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/exact?" 60 (exact?)
#print axioms t_factor_three_mod_four_bare__exact_
theorem t_factor_three_mod_four_bare__grind : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/grind" 60 (grind)
#print axioms t_factor_three_mod_four_bare__grind
theorem t_factor_three_mod_four_bare__grind_suggestions : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/grind+suggestions" 60 (grind +suggestions)
#print axioms t_factor_three_mod_four_bare__grind_suggestions
theorem t_factor_three_mod_four_bare__try_ : S_factor_three_mod_four := by unfold S_factor_three_mod_four; attempt "factor_three_mod_four_bare/try?" 60 (try?)
#print axioms t_factor_three_mod_four_bare__try_

theorem t_euclid_mod_four__decide : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/decide" 60 (decide)
#print axioms t_euclid_mod_four__decide
theorem t_euclid_mod_four__norm_num : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/norm_num" 60 (norm_num)
#print axioms t_euclid_mod_four__norm_num
theorem t_euclid_mod_four__simp : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/simp" 60 (simp)
#print axioms t_euclid_mod_four__simp
theorem t_euclid_mod_four__simp_all : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/simp_all" 60 (simp_all)
#print axioms t_euclid_mod_four__simp_all
theorem t_euclid_mod_four__omega : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/omega" 60 (omega)
#print axioms t_euclid_mod_four__omega
theorem t_euclid_mod_four__aesop : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/aesop" 60 (aesop)
#print axioms t_euclid_mod_four__aesop
theorem t_euclid_mod_four__exact_ : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/exact?" 60 (exact?)
#print axioms t_euclid_mod_four__exact_
theorem t_euclid_mod_four__grind : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/grind" 60 (grind)
#print axioms t_euclid_mod_four__grind
theorem t_euclid_mod_four__grind_suggestions : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/grind+suggestions" 60 (grind +suggestions)
#print axioms t_euclid_mod_four__grind_suggestions
theorem t_euclid_mod_four__try_ : S_euclid_mod_four := by unfold S_euclid_mod_four; attempt "euclid_mod_four/try?" 60 (try?)
#print axioms t_euclid_mod_four__try_

theorem t_not_dvd_euclid__decide : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/decide" 60 (decide)
#print axioms t_not_dvd_euclid__decide
theorem t_not_dvd_euclid__norm_num : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/norm_num" 60 (norm_num)
#print axioms t_not_dvd_euclid__norm_num
theorem t_not_dvd_euclid__simp : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/simp" 60 (simp)
#print axioms t_not_dvd_euclid__simp
theorem t_not_dvd_euclid__simp_all : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/simp_all" 60 (simp_all)
#print axioms t_not_dvd_euclid__simp_all
theorem t_not_dvd_euclid__omega : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/omega" 60 (omega)
#print axioms t_not_dvd_euclid__omega
theorem t_not_dvd_euclid__aesop : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/aesop" 60 (aesop)
#print axioms t_not_dvd_euclid__aesop
theorem t_not_dvd_euclid__exact_ : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/exact?" 60 (exact?)
#print axioms t_not_dvd_euclid__exact_
theorem t_not_dvd_euclid__grind : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/grind" 60 (grind)
#print axioms t_not_dvd_euclid__grind
theorem t_not_dvd_euclid__grind_suggestions : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/grind+suggestions" 60 (grind +suggestions)
#print axioms t_not_dvd_euclid__grind_suggestions
theorem t_not_dvd_euclid__try_ : S_not_dvd_euclid := by unfold S_not_dvd_euclid; attempt "not_dvd_euclid/try?" 60 (try?)
#print axioms t_not_dvd_euclid__try_

theorem t_dvd_factorial__decide : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/decide" 60 (decide)
#print axioms t_dvd_factorial__decide
theorem t_dvd_factorial__norm_num : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/norm_num" 60 (norm_num)
#print axioms t_dvd_factorial__norm_num
theorem t_dvd_factorial__simp : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/simp" 60 (simp)
#print axioms t_dvd_factorial__simp
theorem t_dvd_factorial__simp_all : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/simp_all" 60 (simp_all)
#print axioms t_dvd_factorial__simp_all
theorem t_dvd_factorial__omega : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/omega" 60 (omega)
#print axioms t_dvd_factorial__omega
theorem t_dvd_factorial__aesop : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/aesop" 60 (aesop)
#print axioms t_dvd_factorial__aesop
theorem t_dvd_factorial__exact_ : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/exact?" 60 (exact?)
#print axioms t_dvd_factorial__exact_
theorem t_dvd_factorial__grind : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/grind" 60 (grind)
#print axioms t_dvd_factorial__grind
theorem t_dvd_factorial__grind_suggestions : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/grind+suggestions" 60 (grind +suggestions)
#print axioms t_dvd_factorial__grind_suggestions
theorem t_dvd_factorial__try_ : S_dvd_factorial := by unfold S_dvd_factorial; attempt "dvd_factorial/try?" 60 (try?)
#print axioms t_dvd_factorial__try_

theorem t_euclid__decide : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/decide" 60 (decide)
#print axioms t_euclid__decide
theorem t_euclid__norm_num : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/norm_num" 60 (norm_num)
#print axioms t_euclid__norm_num
theorem t_euclid__simp : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/simp" 60 (simp)
#print axioms t_euclid__simp
theorem t_euclid__simp_all : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/simp_all" 60 (simp_all)
#print axioms t_euclid__simp_all
theorem t_euclid__omega : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/omega" 60 (omega)
#print axioms t_euclid__omega
theorem t_euclid__aesop : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/aesop" 60 (aesop)
#print axioms t_euclid__aesop
theorem t_euclid__exact_ : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/exact?" 60 (exact?)
#print axioms t_euclid__exact_
theorem t_euclid__grind : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/grind" 60 (grind)
#print axioms t_euclid__grind
theorem t_euclid__grind_suggestions : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/grind+suggestions" 60 (grind +suggestions)
#print axioms t_euclid__grind_suggestions
theorem t_euclid__try_ : S_factor_three_mod_four → S_euclid_mod_four → S_not_dvd_euclid → S_dvd_factorial → S_root := by intro h0 h1 h2 h3; unfold S_factor_three_mod_four at h0; unfold S_euclid_mod_four at h1; unfold S_not_dvd_euclid at h2; unfold S_dvd_factorial at h3; unfold S_root; attempt "euclid/try?" 60 (try?)
#print axioms t_euclid__try_

theorem t_set_form__decide : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/decide" 60 (decide)
#print axioms t_set_form__decide
theorem t_set_form__norm_num : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/norm_num" 60 (norm_num)
#print axioms t_set_form__norm_num
theorem t_set_form__simp : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/simp" 60 (simp)
#print axioms t_set_form__simp
theorem t_set_form__simp_all : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/simp_all" 60 (simp_all)
#print axioms t_set_form__simp_all
theorem t_set_form__omega : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/omega" 60 (omega)
#print axioms t_set_form__omega
theorem t_set_form__aesop : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/aesop" 60 (aesop)
#print axioms t_set_form__aesop
theorem t_set_form__exact_ : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/exact?" 60 (exact?)
#print axioms t_set_form__exact_
theorem t_set_form__grind : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/grind" 60 (grind)
#print axioms t_set_form__grind
theorem t_set_form__grind_suggestions : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/grind+suggestions" 60 (grind +suggestions)
#print axioms t_set_form__grind_suggestions
theorem t_set_form__try_ : S_root → S_root_set := by intro h0; unfold S_root at h0; unfold S_root_set; attempt "set_form/try?" 60 (try?)
#print axioms t_set_form__try_

theorem t_odd_factor_three__decide : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/decide" 60 (decide)
#print axioms t_odd_factor_three__decide
theorem t_odd_factor_three__norm_num : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/norm_num" 60 (norm_num)
#print axioms t_odd_factor_three__norm_num
theorem t_odd_factor_three__simp : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/simp" 60 (simp)
#print axioms t_odd_factor_three__simp
theorem t_odd_factor_three__simp_all : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/simp_all" 60 (simp_all)
#print axioms t_odd_factor_three__simp_all
theorem t_odd_factor_three__omega : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/omega" 60 (omega)
#print axioms t_odd_factor_three__omega
theorem t_odd_factor_three__aesop : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/aesop" 60 (aesop)
#print axioms t_odd_factor_three__aesop
theorem t_odd_factor_three__exact_ : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/exact?" 60 (exact?)
#print axioms t_odd_factor_three__exact_
theorem t_odd_factor_three__grind : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/grind" 60 (grind)
#print axioms t_odd_factor_three__grind
theorem t_odd_factor_three__grind_suggestions : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/grind+suggestions" 60 (grind +suggestions)
#print axioms t_odd_factor_three__grind_suggestions
theorem t_odd_factor_three__try_ : S_odd_factor_three := by unfold S_odd_factor_three; attempt "odd_factor_three/try?" 60 (try?)
#print axioms t_odd_factor_three__try_

theorem t_euclid_mod_four_any__decide : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/decide" 60 (decide)
#print axioms t_euclid_mod_four_any__decide
theorem t_euclid_mod_four_any__norm_num : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/norm_num" 60 (norm_num)
#print axioms t_euclid_mod_four_any__norm_num
theorem t_euclid_mod_four_any__simp : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/simp" 60 (simp)
#print axioms t_euclid_mod_four_any__simp
theorem t_euclid_mod_four_any__simp_all : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/simp_all" 60 (simp_all)
#print axioms t_euclid_mod_four_any__simp_all
theorem t_euclid_mod_four_any__omega : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/omega" 60 (omega)
#print axioms t_euclid_mod_four_any__omega
theorem t_euclid_mod_four_any__aesop : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/aesop" 60 (aesop)
#print axioms t_euclid_mod_four_any__aesop
theorem t_euclid_mod_four_any__exact_ : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/exact?" 60 (exact?)
#print axioms t_euclid_mod_four_any__exact_
theorem t_euclid_mod_four_any__grind : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/grind" 60 (grind)
#print axioms t_euclid_mod_four_any__grind
theorem t_euclid_mod_four_any__grind_suggestions : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/grind+suggestions" 60 (grind +suggestions)
#print axioms t_euclid_mod_four_any__grind_suggestions
theorem t_euclid_mod_four_any__try_ : S_euclid_mod_four_any := by unfold S_euclid_mod_four_any; attempt "euclid_mod_four_any/try?" 60 (try?)
#print axioms t_euclid_mod_four_any__try_

theorem t_even_three_mod_four__decide : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/decide" 60 (decide)
#print axioms t_even_three_mod_four__decide
theorem t_even_three_mod_four__norm_num : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/norm_num" 60 (norm_num)
#print axioms t_even_three_mod_four__norm_num
theorem t_even_three_mod_four__simp : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/simp" 60 (simp)
#print axioms t_even_three_mod_four__simp
theorem t_even_three_mod_four__simp_all : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/simp_all" 60 (simp_all)
#print axioms t_even_three_mod_four__simp_all
theorem t_even_three_mod_four__omega : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/omega" 60 (omega)
#print axioms t_even_three_mod_four__omega
theorem t_even_three_mod_four__aesop : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/aesop" 60 (aesop)
#print axioms t_even_three_mod_four__aesop
theorem t_even_three_mod_four__exact_ : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/exact?" 60 (exact?)
#print axioms t_even_three_mod_four__exact_
theorem t_even_three_mod_four__grind : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/grind" 60 (grind)
#print axioms t_even_three_mod_four__grind
theorem t_even_three_mod_four__grind_suggestions : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/grind+suggestions" 60 (grind +suggestions)
#print axioms t_even_three_mod_four__grind_suggestions
theorem t_even_three_mod_four__try_ : S_even_three_mod_four := by unfold S_even_three_mod_four; attempt "even_three_mod_four/try?" 60 (try?)
#print axioms t_even_three_mod_four__try_
