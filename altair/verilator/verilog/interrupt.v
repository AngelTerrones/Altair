// -----------------------------------------------------------------------------
// Copyright (C) 2019 Angel Terrones <angelterrones@gmail.com>
// -----------------------------------------------------------------------------

`default_nettype none
`timescale 1 ns / 1 ps

module interrupt(
        input wire clk,
        input wire rst,
        // bus
        input wire [ 5:0] int_addr,
        input wire [31:0] int_dat_w,
        input wire [ 3:0] int_sel,
        input wire        int_cyc,
        input wire        int_stb,
        input wire [2:0]  int_cti,
        input wire [1:0]  int_bte,
        input wire        int_we,
        output reg [31:0] int_dat_r,
        output reg        int_ack,
        output wire       int_err,
        // interrupt
        output wire [7:0] interrupts
        );
    //--------------------------------------------------------------------------
    reg [7:0] int_reg;  // @BASEADDRESS + 0

    // reg to output
    assign interrupts = int_reg;

    // ACK logic
    always @(posedge clk or posedge rst) begin
        int_ack <= !int_ack && int_cyc && int_stb; // ignore cti and bte
        if (rst) begin
            int_ack <= 0;
        end
    end

    // error logic
    assign int_err = 0;

    // read logic
    always @(posedge clk or posedge rst) begin
        case (int_addr[1:0])
            2'b00: int_dat_r <= {24'b0, int_reg};
            default: int_dat_r <= 32'bx;
        endcase
    end

    // write logic
    always @(posedge clk or posedge rst) begin
        if (int_ack && (&int_sel)) begin
            // verilator lint_off CASEINCOMPLETE
            case (int_addr[1:0])
                2'b00:  int_reg <= int_dat_w[7:0];
            endcase
            // verilator lint_on CASEINCOMPLETE
        end
        if (rst) begin
            int_reg   <= 0;
        end
    end

    //--------------------------------------------------------------------------
    // unused
    wire _unused = |{int_stb, int_cti};
    //--------------------------------------------------------------------------
endmodule
