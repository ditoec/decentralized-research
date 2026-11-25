use anchor_lang::prelude::*;
use anchor_spl::token::{Mint, Token, TokenAccount};

use crate::error::EscrowError;
use crate::state::*;

#[derive(Accounts)]
pub struct InitializeConfig<'info> {
    #[account(mut)]
    pub admin: Signer<'info>,
    #[account(init, payer = admin, space = 8 + Config::INIT_SPACE, seeds = [CONFIG_SEED], bump)]
    pub config: Box<Account<'info, Config>>,
    pub mint: Box<Account<'info, Mint>>,
    #[account(init, payer = admin, seeds = [TREASURY_SEED], bump, token::mint = mint, token::authority = config)]
    pub treasury: Box<Account<'info, TokenAccount>>,
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct UpdateConfig<'info> {
    pub admin: Signer<'info>,
    #[account(mut, seeds = [CONFIG_SEED], bump = config.bump, has_one = admin @ EscrowError::Unauthorized)]
    pub config: Box<Account<'info, Config>>,
}

fn apply(c: &mut Config, p: ConfigParams) -> Result<()> {
    require!(p.sample_ppm <= PPM, EscrowError::BadConfig);
    require!(p.draw_delay >= 1 && p.exec_timeout >= 1, EscrowError::BadConfig);
    // the draw must be possible before an open job can be timed out
    require!(p.dispute_timeout > p.draw_delay, EscrowError::BadConfig);
    require!(p.verifiers.len() <= MAX_VERIFIERS, EscrowError::TooManyVerifiers);
    c.orchestrator = p.orchestrator;
    c.sample_ppm = p.sample_ppm;
    c.draw_delay = p.draw_delay;
    c.exec_timeout = p.exec_timeout;
    c.dispute_timeout = p.dispute_timeout;
    c.verifiers = p.verifiers;
    Ok(())
}

pub fn handle_initialize_config(ctx: Context<InitializeConfig>, params: ConfigParams) -> Result<()> {
    let c = &mut ctx.accounts.config;
    c.admin = ctx.accounts.admin.key();
    c.mint = ctx.accounts.mint.key();
    c.treasury = ctx.accounts.treasury.key();
    c.bump = ctx.bumps.config;
    c.treasury_bump = ctx.bumps.treasury;
    apply(c, params)
}

pub fn handle_update_config(ctx: Context<UpdateConfig>, params: ConfigParams) -> Result<()> {
    apply(&mut ctx.accounts.config, params)
}
