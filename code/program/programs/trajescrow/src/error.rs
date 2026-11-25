use anchor_lang::prelude::*;

#[error_code]
pub enum EscrowError {
    #[msg("Instruction not allowed in the job's current state")]
    BadState,
    #[msg("Signer is not allowed to perform this action")]
    Unauthorized,
    #[msg("Invalid configuration parameter")]
    BadConfig,
    #[msg("Too many verifiers")]
    TooManyVerifiers,
    #[msg("Payment must be positive")]
    ZeroPayment,
    #[msg("Provider bond has insufficient free balance")]
    InsufficientBond,
    #[msg("A provider cannot accept its own job")]
    SelfDealing,
    #[msg("The execution deadline has passed")]
    DeadlinePassed,
    #[msg("Draw delay has not elapsed: the target slot hash is not available yet")]
    DrawTooEarly,
    #[msg("Target slot hash has left the SlotHashes window")]
    SlotHashExpired,
    #[msg("Invalid SlotHashes sysvar data")]
    BadSlotHashes,
    #[msg("Signer is not a registered verifier")]
    NotVerifier,
    #[msg("A node never verifies its own job")]
    SelfVerification,
    #[msg("The second verifier must differ from the first")]
    SameVerifier,
    #[msg("Verifier must commit before it reveals, once each")]
    CommitOrder,
    #[msg("Verdict must be pass, fail or inconclusive")]
    BadVerdict,
    #[msg("Dispute already escalated")]
    AlreadyEscalated,
    #[msg("Dispute not escalated yet")]
    NotEscalated,
    #[msg("Job already settled")]
    AlreadySettled,
    #[msg("Timeout not reached")]
    TimeoutNotReached,
    #[msg("A required token account is missing or wrong")]
    MissingAccount,
    #[msg("Arithmetic overflow")]
    Overflow,
}
