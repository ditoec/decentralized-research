/**
 * Program IDL in camelCase format in order to be used in JS/TS.
 *
 * Note that this is only a type helper and is not the actual IDL. The original
 * IDL can be found at `target/idl/trajescrow.json`.
 */
export type Trajescrow = {
  "address": "HmMX8b7GLwUeJv4dw42xHAryRVfQm319ArWNbfj9ePpf",
  "metadata": {
    "name": "trajescrow",
    "version": "0.1.0",
    "spec": "0.1.0",
    "description": "Escrow, provider bond, delayed slot-hash sampling and 2-of-3 adjudication for trajectory-verified diffusion jobs (runbook section 7)"
  },
  "instructions": [
    {
      "name": "acceptJob",
      "discriminator": [
        43,
        201,
        124,
        1,
        19,
        189,
        96,
        10
      ],
      "accounts": [
        {
          "name": "provider",
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "providerBond",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100
                ]
              },
              {
                "kind": "account",
                "path": "provider"
              }
            ]
          }
        }
      ],
      "args": []
    },
    {
      "name": "commitResult",
      "discriminator": [
        45,
        73,
        224,
        222,
        48,
        67,
        191,
        185
      ],
      "accounts": [
        {
          "name": "provider",
          "signer": true
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        }
      ],
      "args": [
        {
          "name": "merkleRoot",
          "type": {
            "array": [
              "u8",
              32
            ]
          }
        },
        {
          "name": "outputDigest",
          "type": {
            "array": [
              "u8",
              32
            ]
          }
        }
      ]
    },
    {
      "name": "createJob",
      "discriminator": [
        178,
        130,
        217,
        110,
        100,
        27,
        82,
        119
      ],
      "accounts": [
        {
          "name": "requester",
          "writable": true,
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "mint"
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "arg",
                "path": "jobId"
              }
            ]
          }
        },
        {
          "name": "vault",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job"
              }
            ]
          }
        },
        {
          "name": "requesterToken",
          "writable": true
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        }
      ],
      "args": [
        {
          "name": "jobId",
          "type": "u64"
        },
        {
          "name": "payment",
          "type": "u64"
        },
        {
          "name": "verifierFee",
          "type": "u64"
        },
        {
          "name": "bond",
          "type": "u64"
        }
      ]
    },
    {
      "name": "depositBond",
      "discriminator": [
        120,
        89,
        18,
        253,
        112,
        125,
        87,
        255
      ],
      "accounts": [
        {
          "name": "provider",
          "signer": true,
          "relations": [
            "providerBond"
          ]
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "providerBond",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100
                ]
              },
              {
                "kind": "account",
                "path": "provider"
              }
            ]
          }
        },
        {
          "name": "bondVault",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100,
                  95,
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "provider"
              }
            ]
          }
        },
        {
          "name": "providerToken",
          "writable": true
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        }
      ],
      "args": [
        {
          "name": "amount",
          "type": "u64"
        }
      ]
    },
    {
      "name": "drawSample",
      "discriminator": [
        86,
        120,
        70,
        246,
        104,
        34,
        82,
        150
      ],
      "accounts": [
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "slotHashes",
          "address": "SysvarS1otHashes111111111111111111111111111"
        }
      ],
      "args": []
    },
    {
      "name": "escalate",
      "discriminator": [
        123,
        99,
        100,
        10,
        66,
        238,
        154,
        23
      ],
      "accounts": [
        {
          "name": "caller",
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        }
      ],
      "args": []
    },
    {
      "name": "finalVerdict",
      "discriminator": [
        23,
        199,
        72,
        70,
        33,
        187,
        26,
        205
      ],
      "accounts": [
        {
          "name": "verifier",
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        }
      ],
      "args": [
        {
          "name": "msg",
          "type": {
            "defined": {
              "name": "verdictMsg"
            }
          }
        }
      ]
    },
    {
      "name": "initializeConfig",
      "discriminator": [
        208,
        127,
        21,
        1,
        194,
        190,
        196,
        70
      ],
      "accounts": [
        {
          "name": "admin",
          "writable": true,
          "signer": true
        },
        {
          "name": "config",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "mint"
        },
        {
          "name": "treasury",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  116,
                  114,
                  101,
                  97,
                  115,
                  117,
                  114,
                  121
                ]
              }
            ]
          }
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        }
      ],
      "args": [
        {
          "name": "params",
          "type": {
            "defined": {
              "name": "configParams"
            }
          }
        }
      ]
    },
    {
      "name": "openBond",
      "discriminator": [
        104,
        15,
        47,
        167,
        89,
        122,
        159,
        22
      ],
      "accounts": [
        {
          "name": "provider",
          "writable": true,
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "mint"
        },
        {
          "name": "providerBond",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100
                ]
              },
              {
                "kind": "account",
                "path": "provider"
              }
            ]
          }
        },
        {
          "name": "bondVault",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100,
                  95,
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "provider"
              }
            ]
          }
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        }
      ],
      "args": []
    },
    {
      "name": "refund",
      "discriminator": [
        2,
        96,
        183,
        251,
        63,
        208,
        46,
        46
      ],
      "accounts": [
        {
          "name": "caller",
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "vault",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job"
              }
            ]
          }
        },
        {
          "name": "requester",
          "writable": true
        },
        {
          "name": "requesterToken",
          "writable": true
        },
        {
          "name": "providerToken",
          "writable": true,
          "optional": true
        },
        {
          "name": "providerBond",
          "writable": true,
          "optional": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100
                ]
              },
              {
                "kind": "account",
                "path": "job.provider",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "bondVault",
          "writable": true,
          "optional": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100,
                  95,
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job.provider",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "treasury",
          "writable": true,
          "optional": true
        },
        {
          "name": "verifier1Token",
          "writable": true,
          "optional": true
        },
        {
          "name": "verifier2Token",
          "writable": true,
          "optional": true
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        }
      ],
      "args": []
    },
    {
      "name": "release",
      "discriminator": [
        253,
        249,
        15,
        206,
        28,
        127,
        193,
        241
      ],
      "accounts": [
        {
          "name": "caller",
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "vault",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job"
              }
            ]
          }
        },
        {
          "name": "requester",
          "writable": true
        },
        {
          "name": "requesterToken",
          "writable": true
        },
        {
          "name": "providerToken",
          "writable": true,
          "optional": true
        },
        {
          "name": "providerBond",
          "writable": true,
          "optional": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100
                ]
              },
              {
                "kind": "account",
                "path": "job.provider",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "bondVault",
          "writable": true,
          "optional": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100,
                  95,
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job.provider",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "treasury",
          "writable": true,
          "optional": true
        },
        {
          "name": "verifier1Token",
          "writable": true,
          "optional": true
        },
        {
          "name": "verifier2Token",
          "writable": true,
          "optional": true
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        }
      ],
      "args": []
    },
    {
      "name": "slash",
      "discriminator": [
        204,
        141,
        18,
        161,
        8,
        177,
        92,
        142
      ],
      "accounts": [
        {
          "name": "caller",
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "vault",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job"
              }
            ]
          }
        },
        {
          "name": "requester",
          "writable": true
        },
        {
          "name": "requesterToken",
          "writable": true
        },
        {
          "name": "providerToken",
          "writable": true,
          "optional": true
        },
        {
          "name": "providerBond",
          "writable": true,
          "optional": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100
                ]
              },
              {
                "kind": "account",
                "path": "job.provider",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "bondVault",
          "writable": true,
          "optional": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100,
                  95,
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job.provider",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "treasury",
          "writable": true,
          "optional": true
        },
        {
          "name": "verifier1Token",
          "writable": true,
          "optional": true
        },
        {
          "name": "verifier2Token",
          "writable": true,
          "optional": true
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        }
      ],
      "args": []
    },
    {
      "name": "submitVerdict",
      "discriminator": [
        138,
        102,
        56,
        22,
        229,
        130,
        105,
        118
      ],
      "accounts": [
        {
          "name": "verifier",
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        }
      ],
      "args": [
        {
          "name": "msg",
          "type": {
            "defined": {
              "name": "verdictMsg"
            }
          }
        }
      ]
    },
    {
      "name": "timeoutRefund",
      "discriminator": [
        194,
        205,
        141,
        37,
        231,
        118,
        147,
        9
      ],
      "accounts": [
        {
          "name": "caller",
          "signer": true
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "job",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  106,
                  111,
                  98
                ]
              },
              {
                "kind": "account",
                "path": "job.jobId",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "vault",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job"
              }
            ]
          }
        },
        {
          "name": "requester",
          "writable": true
        },
        {
          "name": "requesterToken",
          "writable": true
        },
        {
          "name": "providerToken",
          "writable": true,
          "optional": true
        },
        {
          "name": "providerBond",
          "writable": true,
          "optional": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100
                ]
              },
              {
                "kind": "account",
                "path": "job.provider",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "bondVault",
          "writable": true,
          "optional": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100,
                  95,
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "job.provider",
                "account": "job"
              }
            ]
          }
        },
        {
          "name": "treasury",
          "writable": true,
          "optional": true
        },
        {
          "name": "verifier1Token",
          "writable": true,
          "optional": true
        },
        {
          "name": "verifier2Token",
          "writable": true,
          "optional": true
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        }
      ],
      "args": []
    },
    {
      "name": "updateConfig",
      "discriminator": [
        29,
        158,
        252,
        191,
        10,
        83,
        219,
        99
      ],
      "accounts": [
        {
          "name": "admin",
          "signer": true,
          "relations": [
            "config"
          ]
        },
        {
          "name": "config",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        }
      ],
      "args": [
        {
          "name": "params",
          "type": {
            "defined": {
              "name": "configParams"
            }
          }
        }
      ]
    },
    {
      "name": "withdrawBond",
      "discriminator": [
        222,
        199,
        141,
        31,
        188,
        93,
        155,
        40
      ],
      "accounts": [
        {
          "name": "provider",
          "signer": true,
          "relations": [
            "providerBond"
          ]
        },
        {
          "name": "config",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  99,
                  111,
                  110,
                  102,
                  105,
                  103
                ]
              }
            ]
          }
        },
        {
          "name": "providerBond",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100
                ]
              },
              {
                "kind": "account",
                "path": "provider"
              }
            ]
          }
        },
        {
          "name": "bondVault",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  98,
                  111,
                  110,
                  100,
                  95,
                  118,
                  97,
                  117,
                  108,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "provider"
              }
            ]
          }
        },
        {
          "name": "providerToken",
          "writable": true
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        }
      ],
      "args": [
        {
          "name": "amount",
          "type": "u64"
        }
      ]
    }
  ],
  "accounts": [
    {
      "name": "config",
      "discriminator": [
        155,
        12,
        170,
        224,
        30,
        250,
        204,
        130
      ]
    },
    {
      "name": "job",
      "discriminator": [
        75,
        124,
        80,
        203,
        161,
        180,
        202,
        80
      ]
    },
    {
      "name": "providerBond",
      "discriminator": [
        119,
        123,
        46,
        100,
        18,
        252,
        49,
        237
      ]
    }
  ],
  "events": [
    {
      "name": "drawn",
      "discriminator": [
        87,
        120,
        94,
        189,
        167,
        148,
        44,
        221
      ]
    },
    {
      "name": "settled",
      "discriminator": [
        232,
        210,
        40,
        17,
        142,
        124,
        145,
        238
      ]
    },
    {
      "name": "transition",
      "discriminator": [
        39,
        140,
        137,
        247,
        64,
        71,
        136,
        239
      ]
    }
  ],
  "errors": [
    {
      "code": 6000,
      "name": "badState",
      "msg": "Instruction not allowed in the job's current state"
    },
    {
      "code": 6001,
      "name": "unauthorized",
      "msg": "Signer is not allowed to perform this action"
    },
    {
      "code": 6002,
      "name": "badConfig",
      "msg": "Invalid configuration parameter"
    },
    {
      "code": 6003,
      "name": "tooManyVerifiers",
      "msg": "Too many verifiers"
    },
    {
      "code": 6004,
      "name": "zeroPayment",
      "msg": "Payment must be positive"
    },
    {
      "code": 6005,
      "name": "insufficientBond",
      "msg": "Provider bond has insufficient free balance"
    },
    {
      "code": 6006,
      "name": "selfDealing",
      "msg": "A provider cannot accept its own job"
    },
    {
      "code": 6007,
      "name": "deadlinePassed",
      "msg": "The execution deadline has passed"
    },
    {
      "code": 6008,
      "name": "drawTooEarly",
      "msg": "Draw delay has not elapsed: the target slot hash is not available yet"
    },
    {
      "code": 6009,
      "name": "slotHashExpired",
      "msg": "Target slot hash has left the SlotHashes window"
    },
    {
      "code": 6010,
      "name": "badSlotHashes",
      "msg": "Invalid SlotHashes sysvar data"
    },
    {
      "code": 6011,
      "name": "notVerifier",
      "msg": "Signer is not a registered verifier"
    },
    {
      "code": 6012,
      "name": "selfVerification",
      "msg": "A node never verifies its own job"
    },
    {
      "code": 6013,
      "name": "sameVerifier",
      "msg": "The second verifier must differ from the first"
    },
    {
      "code": 6014,
      "name": "commitOrder",
      "msg": "Verifier must commit before it reveals, once each"
    },
    {
      "code": 6015,
      "name": "badVerdict",
      "msg": "Verdict must be pass, fail or inconclusive"
    },
    {
      "code": 6016,
      "name": "alreadyEscalated",
      "msg": "Dispute already escalated"
    },
    {
      "code": 6017,
      "name": "notEscalated",
      "msg": "Dispute not escalated yet"
    },
    {
      "code": 6018,
      "name": "alreadySettled",
      "msg": "Job already settled"
    },
    {
      "code": 6019,
      "name": "timeoutNotReached",
      "msg": "Timeout not reached"
    },
    {
      "code": 6020,
      "name": "missingAccount",
      "msg": "A required token account is missing or wrong"
    },
    {
      "code": 6021,
      "name": "overflow",
      "msg": "Arithmetic overflow"
    }
  ],
  "types": [
    {
      "name": "config",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "admin",
            "type": "pubkey"
          },
          {
            "name": "orchestrator",
            "type": "pubkey"
          },
          {
            "name": "mint",
            "type": "pubkey"
          },
          {
            "name": "treasury",
            "type": "pubkey"
          },
          {
            "name": "samplePpm",
            "type": "u32"
          },
          {
            "name": "drawDelay",
            "type": "u64"
          },
          {
            "name": "execTimeout",
            "type": "u64"
          },
          {
            "name": "disputeTimeout",
            "type": "u64"
          },
          {
            "name": "verifiers",
            "type": {
              "vec": "pubkey"
            }
          },
          {
            "name": "bump",
            "type": "u8"
          },
          {
            "name": "treasuryBump",
            "type": "u8"
          }
        ]
      }
    },
    {
      "name": "configParams",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "orchestrator",
            "docs": [
              "Off-chain orchestrator key; may escalate disputes on behalf of either party."
            ],
            "type": "pubkey"
          },
          {
            "name": "samplePpm",
            "docs": [
              "p in parts per million, copied into each job at `create_job`."
            ],
            "type": "u32"
          },
          {
            "name": "drawDelay",
            "docs": [
              "DELAY: `draw_sample` uses the slot hash of `commit_slot + draw_delay` (or the first produced slot after it)."
            ],
            "type": "u64"
          },
          {
            "name": "execTimeout",
            "docs": [
              "Slots the provider has after `accept_job` to `commit_result`."
            ],
            "type": "u64"
          },
          {
            "name": "disputeTimeout",
            "docs": [
              "Slots after the execution deadline until any open job can be refunded by `timeout_refund`."
            ],
            "type": "u64"
          },
          {
            "name": "verifiers",
            "docs": [
              "Registered verifier pool (a verifier never verifies its own job; enforced per job)."
            ],
            "type": {
              "vec": "pubkey"
            }
          }
        ]
      }
    },
    {
      "name": "drawn",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "jobId",
            "type": "u64"
          },
          {
            "name": "drawSlot",
            "type": "u64"
          },
          {
            "name": "drawSeed",
            "type": {
              "array": [
                "u8",
                32
              ]
            }
          },
          {
            "name": "sampled",
            "type": "bool"
          }
        ]
      }
    },
    {
      "name": "job",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "jobId",
            "type": "u64"
          },
          {
            "name": "requester",
            "type": "pubkey"
          },
          {
            "name": "provider",
            "type": "pubkey"
          },
          {
            "name": "payment",
            "docs": [
              "P"
            ],
            "type": "u64"
          },
          {
            "name": "verifierFee",
            "type": "u64"
          },
          {
            "name": "bond",
            "docs": [
              "B"
            ],
            "type": "u64"
          },
          {
            "name": "samplePpm",
            "type": "u32"
          },
          {
            "name": "state",
            "type": {
              "defined": {
                "name": "jobState"
              }
            }
          },
          {
            "name": "createdSlot",
            "type": "u64"
          },
          {
            "name": "acceptSlot",
            "type": "u64"
          },
          {
            "name": "execDeadline",
            "type": "u64"
          },
          {
            "name": "finalDeadline",
            "type": "u64"
          },
          {
            "name": "commitSlot",
            "type": "u64"
          },
          {
            "name": "merkleRoot",
            "type": {
              "array": [
                "u8",
                32
              ]
            }
          },
          {
            "name": "outputDigest",
            "type": {
              "array": [
                "u8",
                32
              ]
            }
          },
          {
            "name": "drawSlot",
            "docs": [
              "Slot whose hash seeded the draw, and the draw seed H(slot_hash || job_id_le)."
            ],
            "type": "u64"
          },
          {
            "name": "drawSeed",
            "type": {
              "array": [
                "u8",
                32
              ]
            }
          },
          {
            "name": "sampled",
            "type": "bool"
          },
          {
            "name": "verifier1",
            "type": "pubkey"
          },
          {
            "name": "v1Commitment",
            "type": {
              "array": [
                "u8",
                32
              ]
            }
          },
          {
            "name": "v1Verdict",
            "type": {
              "defined": {
                "name": "verdict"
              }
            }
          },
          {
            "name": "escalated",
            "type": "bool"
          },
          {
            "name": "verifier2",
            "type": "pubkey"
          },
          {
            "name": "v2Commitment",
            "type": {
              "array": [
                "u8",
                32
              ]
            }
          },
          {
            "name": "v2Verdict",
            "type": {
              "defined": {
                "name": "verdict"
              }
            }
          },
          {
            "name": "slashed",
            "docs": [
              "Closed-refunded with the bond forfeited (both verifiers against the provider)."
            ],
            "type": "bool"
          },
          {
            "name": "settled",
            "type": "bool"
          },
          {
            "name": "bump",
            "type": "u8"
          },
          {
            "name": "vaultBump",
            "type": "u8"
          }
        ]
      }
    },
    {
      "name": "jobState",
      "docs": [
        "Lifecycle states of a job (runbook section 7 item 1, manuscript Figure 2)."
      ],
      "type": {
        "kind": "enum",
        "variants": [
          {
            "name": "funded"
          },
          {
            "name": "assigned"
          },
          {
            "name": "committed"
          },
          {
            "name": "underVerification"
          },
          {
            "name": "disputed"
          },
          {
            "name": "closedPaid"
          },
          {
            "name": "closedRefunded"
          },
          {
            "name": "closedUnresolved"
          }
        ]
      }
    },
    {
      "name": "providerBond",
      "docs": [
        "Per-provider bond account. Tokens sit in the provider's bond vault; `accept_job` locks B of the",
        "free balance for the job, settlement unlocks it or (on a confirmed fail) moves it to the treasury."
      ],
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "provider",
            "type": "pubkey"
          },
          {
            "name": "deposited",
            "type": "u64"
          },
          {
            "name": "locked",
            "type": "u64"
          },
          {
            "name": "jobsAccepted",
            "type": "u32"
          },
          {
            "name": "jobsPaid",
            "type": "u32"
          },
          {
            "name": "jobsSlashed",
            "type": "u32"
          },
          {
            "name": "bump",
            "type": "u8"
          },
          {
            "name": "vaultBump",
            "type": "u8"
          }
        ]
      }
    },
    {
      "name": "settled",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "jobId",
            "type": "u64"
          },
          {
            "name": "state",
            "type": {
              "defined": {
                "name": "jobState"
              }
            }
          },
          {
            "name": "toProvider",
            "type": "u64"
          },
          {
            "name": "toRequester",
            "type": "u64"
          },
          {
            "name": "toVerifiers",
            "type": "u64"
          },
          {
            "name": "slashed",
            "type": "u64"
          }
        ]
      }
    },
    {
      "name": "transition",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "jobId",
            "type": "u64"
          },
          {
            "name": "from",
            "type": {
              "defined": {
                "name": "jobState"
              }
            }
          },
          {
            "name": "to",
            "type": {
              "defined": {
                "name": "jobState"
              }
            }
          },
          {
            "name": "slot",
            "type": "u64"
          }
        ]
      }
    },
    {
      "name": "verdict",
      "type": {
        "kind": "enum",
        "variants": [
          {
            "name": "none"
          },
          {
            "name": "pass"
          },
          {
            "name": "fail"
          },
          {
            "name": "inconclusive"
          }
        ]
      }
    },
    {
      "name": "verdictMsg",
      "docs": [
        "A verifier first records a commitment to its own recomputed values (before the provider's",
        "commitment is opened to it), then, in a later transaction, its verdict."
      ],
      "type": {
        "kind": "enum",
        "variants": [
          {
            "name": "commit",
            "fields": [
              {
                "name": "commitment",
                "type": {
                  "array": [
                    "u8",
                    32
                  ]
                }
              }
            ]
          },
          {
            "name": "reveal",
            "fields": [
              {
                "name": "verdict",
                "type": {
                  "defined": {
                    "name": "verdict"
                  }
                }
              }
            ]
          }
        ]
      }
    }
  ]
};
