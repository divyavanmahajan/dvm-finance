// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "DVMFinanceKit",
    platforms: [
        .iOS(.v17)
    ],
    products: [
        .library(
            name: "DVMFinanceKit",
            targets: ["DVMFinanceKit"]
        )
    ],
    dependencies: [
        .package(url: "https://github.com/groue/GRDB.swift.git", from: "6.29.0")
    ],
    targets: [
        .target(
            name: "DVMFinanceKit",
            dependencies: [
                .product(name: "GRDB", package: "GRDB.swift")
            ]
        ),
        .testTarget(
            name: "DVMFinanceKitTests",
            dependencies: [
                "DVMFinanceKit"
            ],
            resources: [
                // Golden fixtures (statement files, snapshot .json.gz) generated
                // by the Python code, added starting Phase B/C/D. Empty for now.
                .copy("Fixtures")
            ]
        )
    ]
)
