// -----------------------------------------------------------------------------
// Copyright (C) 2019 Angel Terrones <angelterrones@gmail.com>
// -----------------------------------------------------------------------------

`default_nettype none
`timescale 1 ns / 1 ps

// from https://github.com/openrisc/orpsoc-cores/blob/master/cores/wb_common/wb_common.v
function is_last;
    input [2:0] cti;
    begin
        case (cti)
            3'b000: is_last = 1;  // classic
            3'b001: is_last = 0;  // constant
            3'b010: is_last = 0;  // increment
            3'b111: is_last = 1;  // end
            default: $display("RAM: illegal Wishbone B4 cycle type (%b)", cti);
        endcase
    end
endfunction

// from https://github.com/openrisc/orpsoc-cores/blob/master/cores/wb_common/wb_common.v
function [31:0] wb_next_addr;
    input [31:0] addr_i;
    input [2:0]  cti_i;
    input [1:0]  bte_i;
    input integer dw;

    reg [31:0] addr;
    integer shift;

    begin
        shift = $clog2(dw/8);
        addr = addr_i >> shift;
        if (cti_i == 3'b010) begin
            case (bte_i)
                2'b00: addr = addr + 1;  // linear
                2'b01: addr = {addr[31:2], addr[1:0] + 2'd1}; // wrap4
                2'b10: addr = {addr[31:3], addr[2:0] + 3'd1}; // wrap8
                2'b11: addr = {addr[31:4], addr[3:0] + 4'd1}; // wrap16
            endcase
        end
        wb_next_addr = addr << shift;
    end
endfunction

module ram #(
             parameter ADDR_WIDTH = 20,
             parameter BASE_ADDR  = 32'h0000_0000
             )(
               input wire clk,
               input wire rst,
               // Data
               input wire [ADDR_WIDTH - 1:0] dwbs_addr,
               input wire [31:0]             dwbs_dat_w,
               input wire [ 3:0]             dwbs_sel,
               input wire                    dwbs_cyc,
               input wire                    dwbs_stb,
               input wire [2:0]              dwbs_cti,
               input wire [1:0]              dwbs_bte,
               input wire                    dwbs_we,
               output reg [31:0]             dwbs_dat_r,
               output reg                    dwbs_ack
               );
    //--------------------------------------------------------------------------
    localparam BYTE_ADDR_WIDTH = ADDR_WIDTH + 2;
    localparam BYTES           = 2**(BYTE_ADDR_WIDTH);
    //
    byte  mem[0:BYTES - 1]; // FFS, this MUST BE BYTE, FOR DPI.

    wire [ADDR_WIDTH + 2 - 1:0] _d_addr;
    wire [ADDR_WIDTH + 2 - 1:0] d_addr;
    wire [ADDR_WIDTH + 2 - 1:0] d_nxt_addr;
    wire                        d_valid;
    reg                         d_valid_r;
    wire                        d_last;

    // read/write data
    assign _d_addr    = {dwbs_addr, 2'b0};  // extend the address
    assign d_nxt_addr = wb_next_addr(_d_addr, dwbs_cti, dwbs_bte, 32);
    assign d_addr     = ((d_valid & !d_valid_r) | d_last) ? _d_addr : d_nxt_addr;
    assign d_last     = is_last(dwbs_cti);
    assign d_valid    = dwbs_cyc && dwbs_stb;

    always @(posedge clk) begin
        dwbs_dat_r <= 32'hx;
        if (dwbs_we && d_valid && dwbs_ack) begin
            if (dwbs_sel[0]) mem[d_addr + 0] <= dwbs_dat_w[0+:8];
            if (dwbs_sel[1]) mem[d_addr + 1] <= dwbs_dat_w[8+:8];
            if (dwbs_sel[2]) mem[d_addr + 2] <= dwbs_dat_w[16+:8];
            if (dwbs_sel[3]) mem[d_addr + 3] <= dwbs_dat_w[24+:8];
        end else begin
            dwbs_dat_r[7:0]    <= mem[d_addr + 0];
            dwbs_dat_r[15:8]   <= mem[d_addr + 1];
            dwbs_dat_r[23:16]  <= mem[d_addr + 2];
            dwbs_dat_r[31:24]  <= mem[d_addr + 3];
        end
    end
    always @(posedge clk or posedge rst) begin
        dwbs_ack <= d_valid && (!((dwbs_cti == 3'b000) | (dwbs_cti == 3'b111)) | !dwbs_ack);

        d_valid_r <= d_valid;
        if (rst) begin
            dwbs_ack <= 0;
            d_valid_r  <= 0;
        end
    end
    //--------------------------------------------------------------------------
    // SystemVerilog DPI functions
    export "DPI-C" function ram_v_dpi_read_word;
    export "DPI-C" function ram_v_dpi_read_byte;
    export "DPI-C" function ram_v_dpi_write_word;
    export "DPI-C" function ram_v_dpi_write_byte;
    export "DPI-C" function ram_v_dpi_load;
    import "DPI-C" function void ram_c_dpi_load(input byte mem[], input string filename);
    //
    function int ram_v_dpi_read_word(int address);
        if (address[31:BYTE_ADDR_WIDTH] != BASE_ADDR[31:BYTE_ADDR_WIDTH]) begin
            $display("[RAM read word] Bad address: %h. Abort.\n", address);
            $finish;
        end
        return {mem[address[BYTE_ADDR_WIDTH-1:0] + 3],
                mem[address[BYTE_ADDR_WIDTH-1:0] + 2],
                mem[address[BYTE_ADDR_WIDTH-1:0] + 1],
                mem[address[BYTE_ADDR_WIDTH-1:0] + 0]};
    endfunction
    //
    function byte ram_v_dpi_read_byte(int address);
        if (address[31:BYTE_ADDR_WIDTH] != BASE_ADDR[31:BYTE_ADDR_WIDTH]) begin
            $display("[RAM read byte] Bad address: %h. Abort.\n", address);
            $finish;
        end
        return mem[address[BYTE_ADDR_WIDTH-1:0]];
    endfunction
    //
    function void ram_v_dpi_write_word(int address, int data);
        if (address[31:BYTE_ADDR_WIDTH] != BASE_ADDR[31:BYTE_ADDR_WIDTH]) begin
            $display("[RAM write word] Bad address: %h. Abort.\n", address);
            $finish;
        end
        mem[address[BYTE_ADDR_WIDTH-1:0] + 0] = data[7:0];
        mem[address[BYTE_ADDR_WIDTH-1:0] + 1] = data[15:8];
        mem[address[BYTE_ADDR_WIDTH-1:0] + 2] = data[23:16];
        mem[address[BYTE_ADDR_WIDTH-1:0] + 3] = data[31:24];
    endfunction
    //
    function void ram_v_dpi_write_byte(int address, byte data);
        if (address[31:BYTE_ADDR_WIDTH] != BASE_ADDR[31:BYTE_ADDR_WIDTH]) begin
            $display("[RAM write byte] Bad address: %h. Abort.\n", address);
            $finish;
        end
        mem[address[BYTE_ADDR_WIDTH-1:0]] = data;
    endfunction
    //
    function void ram_v_dpi_load(string filename);
        ram_c_dpi_load(mem, filename);
    endfunction
    //--------------------------------------------------------------------------
    // unused signals: remove verilator warnings about unused signal
    wire _unused = |{dwbs_addr[1:0]};
    //--------------------------------------------------------------------------
endmodule
