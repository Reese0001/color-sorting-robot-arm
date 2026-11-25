#pragma once
#include <stdint.h>
#include <stddef.h>

/* All diagnostic rows have space for 21 characters plus the terminator. */
static inline char *append(char *out, const char *end, const char *s)
{
    while (out < end && *s) *out++ = *s++;
    *out = 0;
    return out;
}
static inline char *decimal(char *out, const char *end, uint32_t n)
{
    char digits[11];
    char *p = digits + sizeof digits - 1;
    *p = 0;
    do {
        *--p = (char)('0' + n % 10);
        n /= 10;
    } while (n);
    return append(out, end, p);
}
static inline void number_line(char *out, size_t size, const char *prefix,
                               uint32_t n, const char *suffix)
{
    const char *end = out + size - 1;
    out = append(out, end, prefix);
    out = decimal(out, end, n);
    append(out, end, suffix);
}
