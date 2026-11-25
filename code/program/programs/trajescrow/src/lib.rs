//! Escrow program for trajectory-verified diffusion jobs (runbook docs/07-runbook.md section 7 item 1).
//! The state machine follows the table there one to one; see code/program/README.md.
pub mod error;
pub mod instructions;
pub mod state;

use anchor_lang::prelude::*;

pub use instructions::*;
pub use state::*;

declare_id!("HmMX8b7GLwUeJv4dw42xHAryRVfQm319ArWNbfj9ePpf");

#[program]
pub mod trajescrow {
    use super::*;

    pub fn initialize_config(ctx: Context<InitializeConfig>, params: ConfigParams) -> Result<()> {
        instructions::config::handle_initialize_config(ctx, params)
    }

    pub fn update_config(ctx: Context<UpdateConfig>, params: ConfigParams) -> Result<()> {
        instructions::config::handle_update_config(ctx, params)
    }

    pub fn open_bond(ctx: Context<OpenBond>) -> Result<()> {
        instructions::bond::handle_open_bond(ctx)
    }

    pub fn deposit_bond(ctx: Context<MoveBond>, amount: u64) -> Result<()> {
        instructions::bond::handle_deposit_bond(ctx, amount)
    }

    pub fn withdraw_bond(ctx: Context<MoveBond>, amount: u64) -> Result<()> {
        instructions::bond::handle_withdraw_bond(ctx, amount)
    }

    pub fn create_job(ctx: Context<CreateJob>, job_id: u64, payment: u64, verifier_fee: u64, bond: u64) -> Result<()> {
        instructions::job::handle_create_job(ctx, job_id, payment, verifier_fee, bond)
    }

    pub fn accept_job(ctx: Context<AcceptJob>) -> Result<()> {
        instructions::job::handle_accept_job(ctx)
    }

    pub fn commit_result(ctx: Context<CommitResult>, merkle_root: [u8; 32], output_digest: [u8; 32]) -> Result<()> {
        instructions::job::handle_commit_result(ctx, merkle_root, output_digest)
    }

    pub fn draw_sample(ctx: Context<DrawSample>) -> Result<()> {
        instructions::draw::handle_draw_sample(ctx)
    }

    pub fn submit_verdict(ctx: Context<VerifierAction>, msg: VerdictMsg) -> Result<()> {
        instructions::verdict::handle_submit_verdict(ctx, msg)
    }

    pub fn escalate(ctx: Context<Escalate>) -> Result<()> {
        instructions::verdict::handle_escalate(ctx)
    }

    pub fn final_verdict(ctx: Context<VerifierAction>, msg: VerdictMsg) -> Result<()> {
        instructions::verdict::handle_final_verdict(ctx, msg)
    }

    pub fn release(ctx: Context<Settle>) -> Result<()> {
        instructions::settle::handle_release(ctx)
    }

    pub fn refund(ctx: Context<Settle>) -> Result<()> {
        instructions::settle::handle_refund(ctx)
    }

    pub fn slash(ctx: Context<Settle>) -> Result<()> {
        instructions::settle::handle_slash(ctx)
    }

    pub fn timeout_refund(ctx: Context<Settle>) -> Result<()> {
        instructions::settle::handle_timeout_refund(ctx)
    }
}
