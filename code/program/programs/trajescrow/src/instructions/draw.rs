use anchor_lang::prelude::*;

use crate::error::EscrowError;
use crate::state::*;

pub const SLOT_HASHES_ID: Pubkey = pubkey!("SysvarS1otHashes111111111111111111111111111");

/// Committed -> ClosedPaid (not sampled) or UnderVerification (sampled). Permissionless.
#[derive(Accounts)]
pub struct DrawSample<'info> {
    #[account(seeds = [CONFIG_SEED], bump = config.bump)]
    pub config: Box<Account<'info, Config>>,
    #[account(mut, seeds = [JOB_SEED, job.job_id.to_le_bytes().as_ref()], bump = job.bump)]
    pub job: Box<Account<'info, Job>>,
    /// CHECK: address-constrained to the SlotHashes sysvar; parsed by hand (too large to deserialize).
    #[account(address = SLOT_HASHES_ID)]
    pub slot_hashes: UncheckedAccount<'info>,
}

/// The SlotHashes entry for `target`, or for the first produced slot after it if `target` was skipped.
/// Layout: u64 count, then `count` entries of (u64 slot, [u8; 32] hash), newest first.
/// The choice is the same for every caller: entries older than the current slot never change.
pub fn slot_hash_at_or_after(data: &[u8], target: u64) -> Result<(u64, [u8; 32])> {
    require!(data.len() >= 8, EscrowError::BadSlotHashes);
    let n = u64::from_le_bytes(data[0..8].try_into().unwrap()) as usize;
    require!(data.len() >= 8 + n * 40, EscrowError::BadSlotHashes);
    let slot_at = |i: usize| u64::from_le_bytes(data[8 + i * 40..16 + i * 40].try_into().unwrap());
    // number of entries with slot >= target (they form a prefix, slots descend)
    let (mut lo, mut hi) = (0usize, n);
    while lo < hi {
        let mid = (lo + hi) / 2;
        if slot_at(mid) >= target {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    require!(lo > 0, EscrowError::DrawTooEarly);
    // every entry is newer than target: the slot hash we need (or an earlier produced one) is gone
    require!(lo < n || slot_at(n - 1) == target, EscrowError::SlotHashExpired);
    let i = lo - 1;
    let mut h = [0u8; 32];
    h.copy_from_slice(&data[16 + i * 40..48 + i * 40]);
    Ok((slot_at(i), h))
}

/// draw_seed = SHA-256(slot_hash || job_id as u64 little-endian).
/// sampled iff floor(u * 1e6 / 2^64) < sample_ppm, with u the first 8 bytes of draw_seed (little-endian).
pub fn draw(slot_hash: &[u8; 32], job_id: u64, sample_ppm: u32) -> ([u8; 32], bool) {
    let seed = solana_sha256_hasher::hashv(&[slot_hash.as_ref(), &job_id.to_le_bytes()]).to_bytes();
    let u = u64::from_le_bytes(seed[0..8].try_into().unwrap()) as u128;
    let draw_ppm = ((u * PPM as u128) >> 64) as u32;
    (seed, draw_ppm < sample_ppm)
}

pub fn handle_draw_sample(ctx: Context<DrawSample>) -> Result<()> {
    let slot = Clock::get()?.slot;
    let delay = ctx.accounts.config.draw_delay;
    let j = &mut ctx.accounts.job;
    require!(j.state == JobState::Committed, EscrowError::BadState);
    let target = j.commit_slot.checked_add(delay).ok_or(EscrowError::Overflow)?;
    require!(slot > target, EscrowError::DrawTooEarly);
    let data = ctx.accounts.slot_hashes.try_borrow_data()?;
    let (draw_slot, hash) = slot_hash_at_or_after(&data, target)?;
    drop(data);
    let (seed, sampled) = draw(&hash, j.job_id, j.sample_ppm);
    j.draw_slot = draw_slot;
    j.draw_seed = seed;
    j.sampled = sampled;
    emit!(Drawn { job_id: j.job_id, draw_slot, draw_seed: seed, sampled });
    j.transition(if sampled { JobState::UnderVerification } else { JobState::ClosedPaid }, slot);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sysvar(slots: &[u64]) -> Vec<u8> {
        let mut d = (slots.len() as u64).to_le_bytes().to_vec();
        for s in slots {
            d.extend_from_slice(&s.to_le_bytes());
            d.extend_from_slice(&[*s as u8; 32]);
        }
        d
    }

    #[test]
    fn picks_target_or_first_later_slot() {
        let d = sysvar(&[110, 108, 105, 104, 100]);
        assert_eq!(slot_hash_at_or_after(&d, 105).unwrap().0, 105);
        assert_eq!(slot_hash_at_or_after(&d, 106).unwrap().0, 108); // 106, 107 skipped
        assert_eq!(slot_hash_at_or_after(&d, 100).unwrap().0, 100);
        assert!(slot_hash_at_or_after(&d, 111).is_err()); // not produced yet
        assert!(slot_hash_at_or_after(&d, 99).is_err()); // left the window
    }

    #[test]
    fn p_bounds() {
        for j in 0..200u64 {
            assert!(!draw(&[7; 32], j, 0).1);
            assert!(draw(&[7; 32], j, PPM).1);
        }
    }
}
