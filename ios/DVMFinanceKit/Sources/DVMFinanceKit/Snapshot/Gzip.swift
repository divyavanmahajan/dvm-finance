import Foundation
import Compression
#if canImport(Darwin)
import Darwin
#endif

/// Table-driven CRC-32 (RFC 1952 §8: polynomial `0xEDB88320` reflected,
/// initial value `0xFFFFFFFF`, final XOR `0xFFFFFFFF`) — the same algorithm
/// `zlib`/Python's `gzip` module use for the 4-byte CRC32 trailer field.
/// Apple's `Compression` framework has no gzip-container support at all (see
/// `Gzip` below), so this has no framework equivalent to call into.
enum CRC32 {
    private static let table: [UInt32] = {
        var table = [UInt32](repeating: 0, count: 256)
        for i in 0..<256 {
            var c = UInt32(i)
            for _ in 0..<8 {
                c = (c & 1 != 0) ? (0xEDB8_8320 ^ (c >> 1)) : (c >> 1)
            }
            table[i] = c
        }
        return table
    }()

    static func checksum(_ data: Data) -> UInt32 {
        var crc: UInt32 = 0xFFFF_FFFF
        for byte in data {
            let index = Int((crc ^ UInt32(byte)) & 0xFF)
            crc = table[index] ^ (crc >> 8)
        }
        return crc ^ 0xFFFF_FFFF
    }
}

enum RawDeflateError: Error {
    case streamInitFailed
    case streamProcessFailed
}

/// Raw-DEFLATE (RFC 1951) encode/decode via Apple's `Compression` framework.
///
/// **Naming trap**: `COMPRESSION_ZLIB` in this framework is *not* the zlib
/// wire format (RFC 1950 — a 2-byte header + DEFLATE body + Adler-32
/// trailer); despite the name, `compression_encode_buffer`/
/// `compression_decode_buffer`/`compression_stream_*` with algorithm
/// `COMPRESSION_ZLIB` produce/consume **raw** DEFLATE with no framing at
/// all. `Gzip` below supplies the RFC 1952 gzip container (header + CRC32 +
/// ISIZE trailer) around this raw stream, matching what Python's `gzip`
/// module does under the hood with its own zlib binding.
///
/// Uses the streaming `compression_stream_*` API rather than the one-shot
/// `compression_decode_buffer`/`compression_encode_buffer` functions because
/// those require a pre-sized destination buffer — fine for encode (DEFLATE
/// output is bounded by input size plus a small constant), but decode's
/// output size is exactly the information gzip's own ISIZE trailer field
/// exists to *avoid* having to know up front. The stream API instead loops,
/// producing output in `chunkSize` pieces until the algorithm reports
/// `COMPRESSION_STATUS_END`.
enum RawDeflate {
    private static let chunkSize = 64 * 1024

    static func inflate(_ input: Data) throws -> Data {
        try run(operation: COMPRESSION_STREAM_DECODE, input: input)
    }

    static func deflate(_ input: Data) throws -> Data {
        try run(operation: COMPRESSION_STREAM_ENCODE, input: input)
    }

    private static func run(operation: compression_stream_operation, input: Data) throws -> Data {
        // Built via `.allocate` + `memset` (zero-fill) rather than a
        // memberwise `compression_stream(...)` initializer: the struct's
        // *field names* (`src_ptr`/`src_size`/`dst_ptr`/`dst_size`/`state`)
        // are stable/documented, but its *declared field order* (which
        // determines a C-struct memberwise initializer's positional/labeled
        // argument order when Swift imports it) is not something this
        // sandbox can verify without the actual `<compression.h>` SDK
        // header — see the reviewer note in the phase report.
        let streamPointer = UnsafeMutablePointer<compression_stream>.allocate(capacity: 1)
        defer { streamPointer.deallocate() }
        memset(streamPointer, 0, MemoryLayout<compression_stream>.size)

        guard compression_stream_init(streamPointer, operation, COMPRESSION_ZLIB) != COMPRESSION_STATUS_ERROR else {
            throw RawDeflateError.streamInitFailed
        }
        defer { compression_stream_destroy(streamPointer) }

        let destinationBuffer = UnsafeMutablePointer<UInt8>.allocate(capacity: chunkSize)
        defer { destinationBuffer.deallocate() }

        var output = Data()
        var status = COMPRESSION_STATUS_OK

        // `compression_stream` requires a non-null `src_ptr` even for a
        // zero-length source; an empty snapshot payload never occurs in
        // practice (the header alone is non-empty JSON), but this keeps the
        // loop well-defined for empty input in tests.
        var inputBytes = [UInt8](input)
        let isEmptyInput = inputBytes.isEmpty
        if isEmptyInput { inputBytes = [0] }

        try inputBytes.withUnsafeMutableBufferPointer { inputPointer -> Void in
            streamPointer.pointee.src_ptr = UnsafePointer(inputPointer.baseAddress!)
            streamPointer.pointee.src_size = isEmptyInput ? 0 : inputPointer.count

            repeat {
                streamPointer.pointee.dst_ptr = destinationBuffer
                streamPointer.pointee.dst_size = chunkSize
                status = compression_stream_process(streamPointer, Int32(COMPRESSION_STREAM_FINALIZE.rawValue))
                let produced = chunkSize - streamPointer.pointee.dst_size
                if produced > 0 {
                    output.append(destinationBuffer, count: produced)
                }
                if status == COMPRESSION_STATUS_ERROR {
                    throw RawDeflateError.streamProcessFailed
                }
            } while status == COMPRESSION_STATUS_OK
        }

        guard status == COMPRESSION_STATUS_END else {
            throw RawDeflateError.streamProcessFailed
        }

        return output
    }
}

enum GzipError: Error {
    case invalidHeader
    case truncated
    case crcMismatch
    case sizeMismatch
}

/// Hand-rolled RFC 1952 gzip container, since Foundation has no gzip API and
/// `Compression`'s `COMPRESSION_ZLIB` is raw DEFLATE only (see `RawDeflate`
/// above) — mirrors what Python's stdlib `gzip.compress`/`gzip.decompress`
/// (used by `core/snapshots.py`'s `export_snapshot`/`read_snapshot`) do
/// automatically.
enum Gzip {
    private static let magicByte0: UInt8 = 0x1f
    private static let magicByte1: UInt8 = 0x8b
    private static let deflateMethod: UInt8 = 8

    // MARK: - Decode

    /// Parses the 10-byte fixed header, skips any optional FEXTRA/FNAME/
    /// FCOMMENT/FHCRC fields per the FLG byte, inflates the raw-DEFLATE
    /// body, then verifies the trailing CRC32 + ISIZE (RFC 1952 §2.3.1)
    /// against the inflated bytes.
    static func decompress(_ blob: Data) throws -> Data {
        let bytes = [UInt8](blob)
        // 10-byte fixed header + at least an empty deflate stream + 8-byte trailer.
        guard bytes.count >= 18 else { throw GzipError.truncated }
        guard bytes[0] == magicByte0, bytes[1] == magicByte1, bytes[2] == deflateMethod else {
            throw GzipError.invalidHeader
        }
        let flags = bytes[3]
        var offset = 10

        if flags & 0x04 != 0 { // FEXTRA: 2-byte LE length, then that many bytes.
            guard offset + 2 <= bytes.count else { throw GzipError.truncated }
            let xlen = Int(bytes[offset]) | (Int(bytes[offset + 1]) << 8)
            offset += 2
            guard offset + xlen <= bytes.count else { throw GzipError.truncated }
            offset += xlen
        }
        if flags & 0x08 != 0 { // FNAME: null-terminated.
            offset = try skipNullTerminated(bytes, from: offset)
        }
        if flags & 0x10 != 0 { // FCOMMENT: null-terminated.
            offset = try skipNullTerminated(bytes, from: offset)
        }
        if flags & 0x02 != 0 { // FHCRC: 2-byte header CRC, not re-verified here.
            guard offset + 2 <= bytes.count else { throw GzipError.truncated }
            offset += 2
        }
        guard offset + 8 <= bytes.count else { throw GzipError.truncated }

        let trailerStart = bytes.count - 8
        let deflateBody = Data(bytes[offset..<trailerStart])
        let trailer = bytes[trailerStart...]

        let expectedCRC = littleEndianUInt32(trailer, offset: trailerStart)
        let expectedISize = littleEndianUInt32(trailer, offset: trailerStart + 4)

        let inflated = try RawDeflate.inflate(deflateBody)

        guard CRC32.checksum(inflated) == expectedCRC else { throw GzipError.crcMismatch }
        guard UInt32(truncatingIfNeeded: inflated.count) == expectedISize else { throw GzipError.sizeMismatch }

        return inflated
    }

    private static func littleEndianUInt32(_ bytes: ArraySlice<UInt8>, offset: Int) -> UInt32 {
        UInt32(bytes[offset])
            | (UInt32(bytes[offset + 1]) << 8)
            | (UInt32(bytes[offset + 2]) << 16)
            | (UInt32(bytes[offset + 3]) << 24)
    }

    private static func skipNullTerminated(_ bytes: [UInt8], from start: Int) throws -> Int {
        var i = start
        while true {
            guard i < bytes.count else { throw GzipError.truncated }
            if bytes[i] == 0 { return i + 1 }
            i += 1
        }
    }

    // MARK: - Encode

    /// Writes a minimal 10-byte header (no FEXTRA/FNAME/FCOMMENT/FHCRC —
    /// `FLG = 0`, matching what Python's `gzip.compress` writes by default),
    /// the raw-DEFLATE body, then the CRC32 + ISIZE trailer, both
    /// little-endian.
    ///
    /// Deviation: `MTIME` is always written as `0` rather than the current
    /// time (Python's `gzip.compress(..., mtime=None)` embeds
    /// `time.time()`). MTIME is purely informational — `decompress` above
    /// never reads it — and a fixed `0` keeps export byte-for-byte
    /// deterministic given the same payload, which the round-trip tests
    /// rely on.
    static func compress(_ data: Data) throws -> Data {
        let deflated = try RawDeflate.deflate(data)

        var header = Data()
        header.append(magicByte0)
        header.append(magicByte1)
        header.append(deflateMethod)
        header.append(0) // FLG: no optional fields
        header.append(contentsOf: [0, 0, 0, 0]) // MTIME = 0
        header.append(0) // XFL
        header.append(255) // OS = unknown

        let crc = CRC32.checksum(data)
        let isize = UInt32(truncatingIfNeeded: data.count)
        var trailer = Data()
        trailer.append(contentsOf: littleEndianBytes(crc))
        trailer.append(contentsOf: littleEndianBytes(isize))

        return header + deflated + trailer
    }

    private static func littleEndianBytes(_ value: UInt32) -> [UInt8] {
        [
            UInt8(truncatingIfNeeded: value),
            UInt8(truncatingIfNeeded: value >> 8),
            UInt8(truncatingIfNeeded: value >> 16),
            UInt8(truncatingIfNeeded: value >> 24),
        ]
    }
}
