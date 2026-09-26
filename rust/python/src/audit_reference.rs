//! ADR-005 audit-reference hashing belongs to the infrastructure adapter, not core policy.

use hmac::{Hmac, KeyInit, Mac};
use sha2::Sha256;
use std::fmt::Write;

pub(crate) fn digest(key: &[u8], canonical_bytes: &[u8]) -> String {
    // HMAC accepts every key length, including the empty key accepted by Python.
    let mut mac = Hmac::<Sha256>::new_from_slice(key).expect("HMAC accepts any key length");
    mac.update(canonical_bytes);

    let mut hex = String::with_capacity(64);
    for byte in mac.finalize().into_bytes() {
        write!(&mut hex, "{byte:02x}").expect("writing to String cannot fail");
    }
    hex
}
