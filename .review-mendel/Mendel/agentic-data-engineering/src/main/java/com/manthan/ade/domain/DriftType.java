package com.manthan.ade.domain;

/**
 * Classification of a schema change between the active version and an incoming batch.
 */
public enum DriftType {
    NONE,
    ADDITIVE,          // only new columns added — safe
    TYPE_CHANGE,       // an existing column changed SQL type
    RENAME_CANDIDATE,  // one column dropped + one added with same type — likely a rename
    BREAKING           // a column was removed (data-loss risk)
}
